import dataclasses
import enum
import typing


Packable: typing.TypeAlias = int | str | bytes


@enum.unique
class TokenType(enum.Enum):
  INTEGER = 1
  BYTES = 2  # Can be fixed or variable length
  HEXSTRING = 3  # Always variable length
  PADDING = 4


@dataclasses.dataclass(frozen=True)
class TokenInfo:
  type_: TokenType
  num_bits: int | None = None  # None means value has variable length
  little_endian: bool = False
  signed: bool = False


_INTEGER_TOKEN_TYPE_NAMES = ("int", "intbe", "intle", "uint", "uintbe", "uintle")


class BitstringParser:
  """
  BitstringParser provides a similar interface to the bitstring library's pack and unpack functions
  but a more efficient implementation. Some key differences:
    1. BitstringParser expects data to be byte-aligned (bitstring on the other hand allows bit-level
       packing/unpacking). For example, "uint:6, uint:2" is allowed but "uint:6, uint:3" is not.
    2. BitstringParser only supports a subset of the tokens that bitstring supports (see TokenType)
    3. BitsringParser requires that any byte-aligned value (i.e. byte-aligned integers or bytes
       objects) or hex value must itself be byte-aligned within the format string. For example,
       "uint:8, uintbe:32" is allowed but "uint:1, uintbe:32" is not.
    4. BitstringParser only allows integers to be signed if they are byte-aligned.

  Like with bitstring, byte-aligned integer types will default to big-endian if left unspecified in
  the BitstringParser format string.
  """

  def __init__(self, fmt: str):
    self._token_infos: list[TokenInfo] = []
    self._parse_format_str(fmt)

  def _parse_format_str(self, fmt: str) -> None:
    tokens = fmt.replace(" ", "").split(",")
    # Track sum of bit lengths for tokens that are not byte-aligned (i.e. non-byte-aligned INTEGER
    # and non-byte-aligned PADDING tokens) so we can enforce that byte-aligned tokens start at
    # byte-aligned positions within the format string
    non_byte_aligned_token_bit_length_sum = 0
    for i, token in enumerate(tokens):
      token_info = self._token_info_for_token(token)
      token_num_bits = token_info.num_bits
      if token_num_bits is None and i != len(tokens) - 1:
        raise ValueError(f"Variable length token ({token}) is not last token")
      # Treat HEXSTRING tokens as byte-aligned (even though not all hexstrings are) at parse time
      # and catch non-byte-aligned hexstrings at pack time
      token_byte_aligned = token_num_bits is None or token_num_bits % 8 == 0
      if token_byte_aligned and non_byte_aligned_token_bit_length_sum % 8 != 0:
        raise ValueError(
            f"Byte-aligned token {token} is not byte-aligned within format string {fmt}",
        )
      if not token_byte_aligned:
        non_byte_aligned_token_bit_length_sum += typing.cast(int, token_num_bits)
      self._token_infos.append(token_info)

    if non_byte_aligned_token_bit_length_sum % 8 != 0:
      # This check doesn't actually guarantee the byte-alignment of the format string due to
      # HEXSTRING tokens (see earlier comment)
      raise ValueError(f"Format string {fmt} is not byte-aligned")

  def _token_info_for_token(self, token: str) -> TokenInfo:
    if token == "bytes":
      return TokenInfo(TokenType.BYTES)
    if token == "hex":
      return TokenInfo(TokenType.HEXSTRING)
    length_separator_idx = token.find(":")
    token_value_length = int(token[length_separator_idx + 1:])
    if token_value_length <= 0:
      raise ValueError(f"Token {token} has value length {token_value_length} < 0")
    token_type_name = token[:length_separator_idx]
    if token_type_name == "bytes":
      return TokenInfo(TokenType.BYTES, token_value_length * 8)
    if token_type_name in _INTEGER_TOKEN_TYPE_NAMES:
      num_bits = token_value_length
      signed = token.startswith("i")
      little_endian = False
      byte_aligned = num_bits % 8 == 0
      if signed and not byte_aligned:
        raise ValueError(f"Signed integer token {token} is not byte-aligned")
      if token_type_name.endswith("le"):
        if num_bits % 8 != 0:
          raise ValueError(f"Little-endian integer token {token} is not byte-aligned")
        little_endian = True
      elif token_type_name.endswith("be"):
        if num_bits % 8 != 0:
          raise ValueError(f"Big-endian integer token {token} is not byte-aligned")
      return TokenInfo(TokenType.INTEGER, num_bits, little_endian, signed)
    if token_type_name == "pad":
      return TokenInfo(TokenType.PADDING, token_value_length)
    raise ValueError(f"Unrecognized token {token}")

  def pack(self, *values: Packable) -> bytes:
    value_iter = iter(values)
    accumulator_uintbe = 0
    accumulator_num_bits = 0
    byte_list = []
    # We immediately append values for byte-aligned tokens to the byte list. For non-byte-aligned
    # INTEGER and non-byte-aligned PADDING tokens, we iterate over the values until the
    # concatenation of their binary representations would be byte-aligned -- that is, until the sum
    # of the number of bits for each value is divisible by 8 -- after which we append the
    # concatanation of these seen values (converted into a bytes object) to the byte list and then
    # look for the next byte-aligned token or concatenation.
    for token_info in self._token_infos:
      try:
        value_for_token = 0 if token_info.type_ == TokenType.PADDING else next(value_iter)
      except StopIteration as e:
        raise ValueError(f"Not enough values to pack: {values}") from e
      num_bits = token_info.num_bits
      token_type = token_info.type_
      if token_type == TokenType.BYTES:
        # b''.join raises exception if not bytes type
        value_for_token = typing.cast(bytes, value_for_token)
        num_bytes = len(value_for_token)
        if num_bits is not None and num_bytes != num_bits // 8:
          raise ValueError(
              f"Bytes value length ({num_bytes}) doesn't match token length "
              f"({num_bits // 8})",
          )
        byte_list.append(value_for_token)
      elif token_type == TokenType.HEXSTRING:
        # bytes.fromhex raises exception if value_for_token is not a byte-aligned hex string
        byte_list.append(bytes.fromhex(typing.cast(str, value_for_token)))
      elif token_type in (TokenType.INTEGER, TokenType.PADDING):
        value_for_token = typing.cast(int, value_for_token)
        num_bits = typing.cast(int, num_bits)
        if num_bits % 8 == 0:
          byte_list.append(
              value_for_token.to_bytes(
                  length=num_bits // 8,
                  byteorder="little" if token_info.little_endian else "big",
                  signed=token_info.signed,
              ),
          )
        else:
          max_value_allowed = 2 ** num_bits - 1
          if not 0 <= value_for_token <= max_value_allowed:
            raise ValueError(
                f"Value {value_for_token} not within allowed range [0, {max_value_allowed}]",
            )
          accumulator_num_bits += num_bits
          accumulator_uintbe <<= num_bits
          accumulator_uintbe |= value_for_token
          if accumulator_num_bits % 8 == 0:
            byte_list.append(
                accumulator_uintbe.to_bytes(
                    length=accumulator_num_bits // 8,
                    byteorder="big",
                ),
            )
            # Reset accumulator state
            accumulator_uintbe = 0
            accumulator_num_bits = 0
      else:
        # Ensure that all new token types get explicitly handled
        raise ValueError(f"Unrecognized token type {token_type}")

    return b''.join(byte_list)

  def unpack(self, data: bytes) -> list[Packable]:
    total_bits = len(data) * 8
    total_bits_processed = 0
    values: list[Packable] = []
    for token_info in self._token_infos:
      num_bits = token_info.num_bits
      token_type = token_info.type_
      if token_info.num_bits is None:
        # Guaranteed by format string parser to be last token
        num_bits = total_bits - total_bits_processed
      num_bits = typing.cast(int, num_bits)
      if token_type == TokenType.PADDING:
        total_bits_processed += num_bits
        continue

      start_byte_index = total_bits_processed // 8
      end_byte_index = (total_bits_processed + num_bits - 1) // 8
      if end_byte_index >= len(data):
        raise IndexError(f"Not enough data to unpack, data: {data!r}")
      # Smallest sequence of bytes that contains the value to extract
      containing_byte_sequence = data[start_byte_index: end_byte_index + 1]

      if token_type == TokenType.BYTES:
        values.append(containing_byte_sequence)
      elif token_type == TokenType.HEXSTRING:
        values.append(containing_byte_sequence.hex())
      elif token_type == TokenType.INTEGER:
        if num_bits % 8 == 0:
          values.append(
              int.from_bytes(
                  containing_byte_sequence,
                  byteorder="little" if token_info.little_endian else "big",
                  signed=token_info.signed,
              ),
          )
        else:
          # The format string parser guarantees that signed integers are byte-aligned, so it's safe
          # to unconditionally use signed=False for this conversion
          containing_byte_sequence_as_uintbe = int.from_bytes(
              containing_byte_sequence,
              byteorder="big",
          )
          # Right shift off bits to the right of the bits that make up the value we want to
          # extract
          containing_value_as_uintbe = containing_byte_sequence_as_uintbe >> (
              (8 * len(containing_byte_sequence) - (total_bits_processed % 8 + num_bits))
          )
          # Mask off any bits that are actually part of previously processed tokens
          value_as_uintbe = containing_value_as_uintbe & ((1 << num_bits) - 1)
          values.append(value_as_uintbe)
      else:
        # Ensure that all new token types get explicitly handled
        raise ValueError(f"Unexpected token type {token_type}")

      total_bits_processed += num_bits

    return values

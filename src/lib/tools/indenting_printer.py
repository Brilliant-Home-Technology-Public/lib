import contextlib
import sys

import lib.serialization as ser


class IndentingPrinter:

  # https://en.wikipedia.org/wiki/ANSI_escape_code#SGR_(Select_Graphic_Rendition)_parameters
  STYLE_CODES = {
      "reset": 0,
      # Font weight/style/decoration
      "bold": 1,
      "dim": 2,
      "italic": 3,
      "underline": 4,
      # Foreground colors
      "red": 31,
      "green": 32,
      "yellow": 33,
      "blue": 34,
      "magenta": 35,
      "cyan": 36,
      "white": 37,
  }

  def __init__(self, tab="  ", outfile=None):
    self._tab = tab
    self._outfile = outfile or sys.stdout
    self._indent = 0

  def _format_escape_sequence(self, requested_styles):
    if not self._outfile.isatty():
      # Disable all styles when output directed to a file
      return ""

    # ESC[<n>m is the ANSI control sequence to set terminal graphics modes
    # Multiple parameters can be supplied if separated by semicolons
    # See https://en.wikipedia.org/wiki/ANSI_escape_code
    # \033 is the octal encoding for ESC
    codes = ";".join([str(self.STYLE_CODES[s.lower()]) for s in requested_styles if s])
    return "\033[{}m".format(codes)

  def write(self, line="", style="", prefix="", suffix=""):
    print(
        "{spacer}{prefix}{start_style}{line}{reset_style}{suffix}".format(
            spacer=self._tab * self._indent,
            prefix=prefix,
            line=line,
            start_style=self._format_escape_sequence(style.split(",")),
            reset_style=self._format_escape_sequence(["reset"]),
            suffix=suffix,
        ),
        file=self._outfile,
    )

  # Same as write but will handle and expand printing of:
  #  1) int, str, bool, None (quotes for strings, plain for int/bool, None for none)
  #  2) lists and dicts (newline for each item / key-val pair)
  #  3) any recognized object type passed in which will call write_object recursively on.
  #  All object properties will be printed on a newline.
  def write_object(self, target_object, style="", prefix="", suffix="", field_to_class_map=None):
    if type(target_object) == str:
      self.write(f"\"{target_object}\"", style=style, prefix=prefix, suffix=",")
    elif target_object is None:
      self.write("None", style=style, prefix=prefix, suffix=",")
    elif (type(target_object) == int or
          type(target_object) == bool):
      self.write(target_object, style=style, prefix=prefix, suffix=",")
    elif hasattr(target_object, 'thrift_spec'):
      with self.indented(header_text=f"{type(target_object).__name__}(", prefix=prefix):
        count = 0
        for key, val in vars(target_object).items():
          self._write_key_value(
              target_key=key,
              target_value=val,
              is_last=count == (len(vars(target_object)) - 1),
              field_to_class_map=field_to_class_map,
              style=style,
          )
          count += 1
      self.write(")", style=style, suffix=suffix)
    elif type(target_object) == dict:
      with self.indented(header_text="{", prefix=prefix):
        count = 0
        for key, val in target_object.items():
          self._write_key_value(
              target_key=key,
              target_value=val,
              is_last=count == (len(target_object) - 1),
              field_to_class_map=field_to_class_map,
              style=style,
          )
          count += 1
      self.write("}", style=style, suffix=suffix)
    elif type(target_object) == list:
      with self.indented(header_text="[", prefix=prefix):
        for item in target_object:
          self.write_object(
              target_object=item,
              style=style,
              prefix=prefix,
              field_to_class_map=field_to_class_map,
          )
      self.write("]", style=style, suffix=suffix)
    else:
      self.write(
          f"Unrecognized Object type: {type(target_object)}",
          prefix=prefix,
          suffix=suffix,
      )

  def _write_key_value(self, target_key, target_value, is_last, field_to_class_map, style):
    # Look for specified serialized thrift structs
    # and attempt ot deserialize them.
    if (type(field_to_class_map) == dict and
        target_key in field_to_class_map
        and type(target_value) == str):
      object_val = ser.deserialize(field_to_class_map[target_key], target_value)
      self.write_object(
          target_object=object_val,
          style=style,
          prefix=f"{target_key}: ",
          suffix="" if is_last else ",",
          field_to_class_map=field_to_class_map,
      )
    else:
      self.write_object(
          target_object=target_value,
          style=style,
          prefix=f"{target_key}: ",
          suffix="" if is_last else ",",
          field_to_class_map=field_to_class_map,
      )

  def adjust_indent(self, add_levels=1):
    self._indent += add_levels

  @contextlib.contextmanager
  def indented(self, header_text=None, header_style="", add_levels=1, prefix=""):
    if header_text:
      self.write(header_text, style=header_style, prefix=prefix)
    self.adjust_indent(add_levels=add_levels)
    try:
      yield
    finally:
      self.adjust_indent(add_levels=-add_levels)

import math


def linear_interpolation_percentile(data: list[float], percentile: float) -> float:
  sorted_data = sorted(data)
  fractional_rank = (len(sorted_data) - 1) * (percentile / 100.0)
  floored_rank = math.floor(fractional_rank)
  if floored_rank == fractional_rank:
    # Coerce value to float, in case data contains non-float elements (e.g. ints)
    return float(sorted_data[floored_rank])
  fraction = fractional_rank - floored_rank
  return sorted_data[floored_rank] + (fraction * (sorted_data[floored_rank + 1] - sorted_data[floored_rank]))

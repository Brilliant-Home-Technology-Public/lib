Peripheral Versioning
=======================

A Peripheral version is different than a normal service version in that it should only contain
two functions, `migrate_variables_up` and `migrate_variables_down`. The functions both accept
a variables map (variable name to string variable value) and a `last_set_timestamps` map (variable name to int timestamp) as arguments, and are expected to return a tuple of both of those
maps. Here is an example migration for the gangbox which changes the scale of the intensity.

```python
class GangboxPeripheralVersion20180221(PeripheralVersion):
  peripheral_name = "gangbox_peripheral_0"
  version = constants.VERSION_20180221

  @classmethod
  def migrate_variables_up(cls, variables, timestamps):
    if "intensity" in variables and variables["intensity"] is not None:
      variables["intensity"] = str(int(variables["intensity"]) / 10)

    return variables, timestamps

  @classmethod
  def migrate_variables_down(cls, variables, timestamps):
    if "intensity" in variables and variables["intensity"] is not None:
      variables["intensity"] = str(int(variables["intensity"]) * 10)
    return variables, timestamps
```

Note that for a given version, you *should not* assume _anything_ about the keys or the values
inside the variables map. It's possible that a given variable name may not be passed into
the variables map, or that the value could be None (i.e. in the case of a deleted variable in
the `ModifiedVariable` struct). It's also possible that not every variable contained in the
variable map will be present in the timestamps map.

Common Migrations
------------------

Here is a migration to change a variable name:

```python
def migrate_variables_up(cls, variables, timestamps):
  if "old_variable" in variables:
    variables["new_variable"] = variables["old_variable"]
    variables.pop("old_variable")
  if "old_variable" in timestamps:
    timestamps["new_variable"] = timestamps["old_variable"]
    timestamps.pop("old_variable")

  return variables, timestamps
```

Here is a migration to add a new variable (maybe based off the value of the old variable):

```python
def migrate_variables_up(cls, variables, timestamps):
  if "old_variable" in variables:
    variables["new_variable"] = str(int(variables["old_variable"]) + 10)
  if "old_variable" in timestamps:
    timestamps["new_variable"] = timestamps["old_variable"]

  return variables, timestamps
```

Here is a migration to complete remove a variable:

```python
def migrate_variables_up(cls, variables, timestamps):
  variables.pop("old_variable", None)
  timestamps.pop("old_variable", None)

  return variables, timestamps
```

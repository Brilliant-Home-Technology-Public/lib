import thrift_types.message_bus.ttypes as mb_ttypes


def update_modified_variables(peripheral_name, modified_variables, updated_map):
  """
  Given a map of updated variables, and the original modified variables, return a list of new
  modified variables to attach to the response.
  """
  to_return = []

  existing_variables = set()
  for modified_variable in modified_variables:
    existing_variables.add(modified_variable.variable_name)
    if modified_variable.variable_name in updated_map:
      variable = updated_map[modified_variable.variable_name]
      if variable:
        # This variable was updated.
        modified_variable.variable = updated_map[modified_variable.variable_name]
        to_return.append(modified_variable)
      # NOTE: if variable is None, that means it was removed, so we should not include it in the
      # final set of ModifiedVariables to return
    else:
      # This variable was not changed, keep it as is.
      to_return.append(modified_variable)

  # Handle any modified variables that were newly added.
  added_variables = set(updated_map.keys()) - existing_variables
  for variable_name in added_variables:
    variable = updated_map[variable_name]
    modified_variable = mb_ttypes.ModifiedVariable(
        variable_name=variable_name,
        variable=variable,
    )
    to_return.append(modified_variable)

  return to_return


def update_variables_map(peripheral_name, variables, updated_map):
  """
  Given a map of variable name to variables, and a map of updated variables, return a mapping
  of new variable names to variables.
  """
  new_variables = {}
  for variable_name, variable in variables.items():
    if variable_name in updated_map:
      variable = updated_map[variable_name]
      if variable:
        # If the variable was changed, add the new variable to the map.
        new_variables[variable_name] = updated_map[variable_name]
      # NOTE: if variable is None, that means it was removed, so we should not include it in the
      # final set of Variables to return
    else:
      # This variable was not changed, keep it as is.
      new_variables[variable_name] = variable

  # Handle any variables that were newly added.
  added_variables = {
      name: variable for name, variable in updated_map.items() if name not in variables
  }
  new_variables.update(added_variables)

  return new_variables

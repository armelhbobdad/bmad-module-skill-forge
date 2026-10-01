# The body of a ruleset PUT or POST, from a ruleset as a GET returns it
# (baseline-ruleset-Default.json, or the live ruleset). Every restore in
# docs/_internal/RELEASING.md runs it with `jq -f`, so a change here changes
# them all; record it with the restore drill in that file.
#
# PUT replaces the ruleset wholesale, so a field left out is reset
# server-side; bypass_actors keeps the admin-via-PR bypass. A GET adds
# do_not_enforce_on_create (and can add a null integration_id) to the
# required_status_checks rule; a PUT that carried them was refused with
# HTTP 422, so the filter drops them. Every other rule parameter is kept as
# the GET returns it.
{name, target, enforcement, conditions,
  rules: [.rules[] | if .type == "required_status_checks" then
    .parameters |= (del(.do_not_enforce_on_create)
      | .required_status_checks |= map(with_entries(select(.value != null))))
  else . end],
  bypass_actors}

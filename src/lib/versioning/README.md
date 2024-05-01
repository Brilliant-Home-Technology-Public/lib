Brilliant API Versioning
=========================

All of `switch-embedded`, `server`, and the mobile clients use the API version negotiated protocol
outlined [here](https://github.com/ramjet-labs/thrift_types/wiki/API-Versioning-Proposal).


Adding a New Version
-----------------------

Versions are defined in the `thrift_types` repo
[`thrift_types/version.thrift`](https://github.com/ramjet-labs/thrift_types/blob/master/version.thrift).
When a developer makes
[a qualifying change to the Thrift schemas](https://github.com/ramjet-labs/thrift_types/blob/master/README.md#rules-for-thrift-files-in-thrift_types),
the developer will also define a new version in the
[`thrift_types/version.thrift`](https://github.com/ramjet-labs/thrift_types/blob/master/version.thrift)
file. When a new version is defined, new classes must be added to all of the top-level modules in
this directory, `lib/versioning`. For example, in
[`remote_bridge_version.py`](remote_bridge_version.py), if the previous code looked like this:

```python
class RemoteBridgeVersion20190716:
    prev_version = None
    version = constants.VERSION_20190716
    next_version = None
```

then after the upgrade to version `VERSION_20200923`, the code would need to be updated to look like
this:

```python
class RemoteBridgeVersion20190716:
    prev_version = None
    version = constants.VERSION_20190716
    next_version = constants.VERSION_20200923


class RemoteBridgeVersion20200923:
    prev_version = constants.VERSION_20190716
    version = constants.VERSION_20200923
    next_version = None
```


Defining a migration for a given function
-------------------------------------------

When defining a migration for a given service's function, the system expects a standardized
`classmethod` to exist in the correct version class. The name of this function will depend on
the service's function name, whether the args or response are being translated, and whether this
is an upgrade or a downgrade.

For example, in `remote_bridge_version.py`, to write an args upgrade for
`forward_set_variables_request` from version 1 to version 2, we would create and define the
following `classmethod`:

```python
class RemoteBridgeVersion1:
    prev_version = None
    version = "1"
    next_version = "2"


class RemoteBridgeVersion2:
    prev_version = "1"
    version = "2"
    next_version = None

    @classmethod
    def _forward_set_variables_request_args_up(cls, args, context=None):
        args = super()._forward_set_variables_request_args_up(args=args, context=context):

        args["arg1"] += 1
        return args
```

Note that the upgrade function for a given version defines how to upgrade *to* the given version,
and the downgrade function for a given version defines how to downgrade *from* that version.


Application-Specific Migrations
------------------

There are instances where Thrift objects need to be migrated differently, depending on its usage or
application. Each of the top-level modules in this directory (except `base_version.py` and
`utils.py`) defines an application-specific migration.

### Property Installations Version

This versioning library was added to handle version migrations for the `device_provision_state`
field and the `post_provision_state` field of the
[`PropertyInstallation` dataclass](https://github.com/ramjet-labs/server/blob/273135cb2a69bf398a12e148d95825c312431a9b/backends/organizations/common/organizations_service/common/interface.py#L206-L214).
These fields are initially set when a
[Mobile client completes a property installation](https://brillianthome.atlassian.net/wiki/spaces/SER/pages/1645969720/End-to-end+installation+flow#Complete-the-installation-for-a-home-POST-%2Fhomes%2F%7Bhome_id%7D%2Fcomplete-installation).
The property installation details are stored in our `organizations.property_installations` table
where we can retrieve them at a later date to reconfigure the property (notably during resident
move-in and move-out). Since the `device_provision_state` and `post_provision_state` fields (and
their underlying Thrift structures) may evolve over time, we have this versioning library to
facilitate translating older versions to a more current version.


Common Migrations
------------------

For help on peripheral specific migrations, look [here](https://github.com/ramjet-labs/lib/tree/master/src/lib/versioning/peripheral_version).

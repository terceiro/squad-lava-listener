# SQUAD LAVA data feed

This project is a link between [LAVA](https://git.linaro.org/lava/) results
(currently v1 only) and [SQUAD dashboard](https://github.com/Linaro/squad).
It allows to establish a reporting dashboard for continuous build and test
environment. Single listener supports multiple LAVA instances and one SQUAD
instance.

In order to set it up for your instance of SQUAD the following settings need
to be updated:

```
SQUAD_URL = "http://localhost:8001/"
SQUAD_TOKENS = {
    'project': 'superSecterProjectToken',
}
```

Similarily for LAVA instances the token dictionary needs to be updated:

```
CREDENTIALS = {
    'host.example.com': ('username', 'password'),
}
```

In order to establish link between build system (i.e. Jenkins) and LAVA, the following API is available:

```
POST /api/pattern/
    "lava_server": "https://validation.linaro.org",
    "lava_job_id": "12346.1",
    "build_job_name": "team/project/build_number",
    "build_job_url": "https://ci.linaro.org/job/my-project/123"}
```

**lava_server** - variable that identifies the URL of the LAVA instance. It has to correspond
to entry in CREDENTIALS dictionary
**lava_job_id** - ID of the job to follow
**build_job_name** - consists of the following: SQUAD team name/project name/build identifier
**build_job_url** - URL that leads to the build system page for this build

Example script (./client.py) was provided to be used with this API.

## License

Copyright © 2016-2017 Linaro Limited

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the
Free Software Foundation, either version 3 of the License, or (at your
option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
Public License for more details.

You should have received a copy of the GNU General Public License along
with this program. If not, see http://www.gnu.org/licenses/.

# DevOps API
|No|Verb |URL|Params|Description|
|:-:|:-:    |:-:|:-:|:-:|
|1| POST    | /api/v1/devops/token | token=TOKEN | Create a SCM token |
|2| GET     | /api/v1/devops/token | - | Get the SCM token of the current user |
|3| PUT     | /api/v1/devops/token | token=TOKEN | Update the SCM token of the current user |
|4| GET     | /api/v1/devops/projects | - | Get the list of projects|
|5| GET     | /api/v1/devops/{project}/pipelines | - | Get the list of pipelines of a specific project|
|6| POST    | /api/v1/devops/{project}/pipelines | variables={key1:value1<br>, ...<br>,keyN:valueN} | Trigger a new pipeline of a specific project|
|7| GET     | /api/v1/devops/{project}/pipelines/{pipeline} | - | Get a specific pipeline of a specific project|
|8| DELETE  | /api/v1/devops/{project}/pipelines/{pipeline} | - | Delete a specific pipeline of a specific project|
|9| POST    | /api/v1/devops/{project}/pipelines/{pipeline}/retry | - | Retry a pipeline|
|10| POST   | /api/v1/devops/{project}/pipelines/{pipeline}/cancel | - | Cancel a pipeline|
|11| Get    | /api/v1/devops/{project}/jobs | - | Get the list of jobs of a specific project|
|12| Get    | /api/v1/devops/{project}/jobs/{pipeline} | - | Get the list of jobs of a specific pipeline|
|13| Get    | /api/v1/devops/{project}/jobs/{job} | - | Get a specific job|
|14| POST   | /api/v1/devops/{project}/jobs/{job}/erase | - | Erase a specific job|
|15| POST   | /api/v1/devops/{project}/jobs/{job}/play | - | Play a specific job|
|16| POST   | /api/v1/devops/{project}/jobs/{job}/retry | - | Retry a specific job|
|17| POST   | /api/v1/devops/{project}/jobs/{job}/cancel | - | Cancel a specific job|
|18| POST   | /api/v1/devops/{project}/jobs/{job}/trace | - | Trace a specific job|
|19| GET    | /api/v1/devops/{project}/pipeline_schedules | - | Get the list of schedules of a specific project|
|20| POST   | /api/v1/devops/{project}/pipeline_schedules | ref=BRANCH<br>, description=DESCRIPTION<br>, cron=CRON_STRING | Create a new pipeline schedule of a specific project|
|21| GET    | /api/v1/devops/{project}/pipeline_schedule/{schedule} | - | Get a specific pipeline schedule of a specific project|
|22| POST   | /api/v1/devops/{project}/pipeline_schedule/{schedule} | - | Play a specific pipeline schedule of a specific project|
|23| PUT    | /api/v1/devops/{project}/pipeline_schedule/{schedule} | ref=BRANCH<br>, description=DESCRIPTION<br>, cron=CRON_STRING | Update a specific pipeline schedule of a specific project|
|24| DELETE | /api/v1/devops/{project}/pipeline_schedule/{schedule} | - | Delete a specific pipeline schedule of a specific project|

## Example
```sh
curl localhost/api/v1/devops/projects -H "Authorization: 1bf68df4f9dccf2134d86a942e040920952dccf4cb0a8f87fd1dc836d0486027"

curl localhost/api/v1/devops/2/pipelines -H "Authorization: 1bf68df4f9dccf2134d86a942e040920952dccf4cb0a8f87fd1dc836d0486027"
curl localhost/api/v1/devops/all/pipelines -H "Authorization: 1bf68df4f9dccf2134d86a942e040920952dccf4cb0a8f87fd1dc836d0486027"

curl localhost/api/v1/devops/2/pipeline_schedules -H "Authorization: 1bf68df4f9dccf2134d86a942e040920952dccf4cb0a8f87fd1dc836d0486027"
curl localhost/api/v1/devops/all/pipeline_schedules -H "Authorization: 1bf68df4f9dccf2134d86a942e040920952dccf4cb0a8f87fd1dc836d0486027"
```

## Dev

```py
import gitlab
gl = gitlab.Gitlab(url="http://10.23.9.108", private_token="glpat-uMAq-Ykp9vUUMoNtWEYx")
gl.projects.list()
```

# Money to Prisoners API Server
The API Server for the Money to Prisoners Project

## Dependencies
### Docker
To run this project locally you need to have
[Docker](http://docs.docker.com/installation/mac/) and
[Docker Compose](https://docs.docker.com/compose/install/) installed.

### Other Repositories
Alongside this repository might need the [Cashbook UI](https://github.com/ministryofjustice/money-to-prisoners-cashbook)
and if you're planning to deploy then you'll need the [deployment repository](https://github.com/ministryofjustice/money-to-prisoners-deploy)

## Developing
### Development Server
#### Boot2Docker
> If you're developing on a Mac then Docker won't run natively, you'll be running
> a single VM with linux installed where your Docker containers run. To start the vm
> run the following first before continuing:
> ```
> $ boot2docker up
> $ eval "$(boot2docker shellinit)"
> ```

In a terminal `cd` into the directory you checked this project out into, then
```
$ docker-compose build
```
Create the database:
```
$ docker-compose run db /bin/bash
$ ./docker-entrypoint.sh postgres &
$ su postgres
$ createdb mtp_api;
$ exit
$ exit
```
Start the containers:
```
$ docker-compose up
```

Wait while Docker does it's stuff and you'll soon see something like:
```
django_1 | Running migrations:
django_1 |   No migrations to apply.
```

#### Using Make

For convenience you can run this using the Makefile provided:

```shell
$ make build # initialise the server
$ make # run the server
```

You should be able to point your browser at
[http://localhost:8000](http://localhost:8000)
if you're using *boot2docker* then it'll be at the IP of the boot2docker virtual machine.
You can find it by typing `boot2docker ip` in a terminal. Then visit http://**boot2docker ip**:8000/

### Using the API
#### Getting an access token
```
curl -X POST -d "grant_type=password&username=<user_name>&password=<password>&client_id=<client_id>&client_secret=<client_secret>" http://localhost:8000/oauth2/token/
```
If you have executed the `./manage.py load_test_data` command then you'll have 
some users and a test oauth2 application already created. In which case execute the following command:
```
curl -X POST -d "grant_type=password&username=test_prison_1&password=test_prison_1&client_id=cashbook&client_secret=cashbook" http://localhost:8000/oauth2/token/
```
Which will return something like:
```
{
    "expires_in": 36000,
    "access_token": "R6mYyIzZQ03Kj95iEoD53FbLPGkL7Y",
    "token_type": "Bearer",
    "scope": "write read",
    "refresh_token": "s57NweoHvPXahvmGklsrdDFMxxNSaf"
}
```
Use the `access_token` in the response in subsequent requests.

#### Retrieve Transactions
```
curl -H "Authorization: Bearer R6mYyIzZQ03Kj95iEoD53FbLPGkL7Y" http://localhost:8000/transactions/
```

The response will be something like this:
```
{
    "count": 6,
    "next": null,
    "previous": null,
    "results": [
        {
            "id": 240,
            "prisoner_number": "R5957RF",
            "prisoner_dob": "1984-09-21",
            "amount": 29339,
            "sender": "RjXqVbLtSzGFIWURj28cQsIg",
            "received_at": "2015-06-11T13:44:57.645000Z"
        },
        ...
        {
            "id": 222,
            "prisoner_number": "E2601NE",
            "prisoner_dob": "1955-08-29",
            "amount": 2841,
            "sender": "Zz5EPK6gIcv5b1yOKqX20PVb",
            "received_at": "2015-06-14T20:41:57.479000Z"
        }
    ]
}
```

If you are using [postman](https://chrome.google.com/webstore/detail/postman-rest-client/fdmmgilgnpjigdojojpjoooidkmcomcm?hl=en)
to make HTTP requests then I have included a [postman
collection](devtools/mtp-api.json) that you can import which sets everything up for you.

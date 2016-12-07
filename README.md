# Money to Prisoners API Server
The API Server for the Money to Prisoners Project

## Dependencies
### Docker
To run this project locally on a Mac you need to have
[Virtualbox](https://www.virtualbox.org/wiki/Downloads)
[Docker](http://docs.docker.com/installation/mac/) and
[Docker Compose](https://docs.docker.com/compose/install/) installed.

### Other Repositories
Alongside this repository you might need the [Cashbook UI](https://github.com/ministryofjustice/money-to-prisoners-cashbook)
and if you're planning to deploy then you'll need the [deployment repository](https://github.com/ministryofjustice/money-to-prisoners-deploy)

## Developing
### Development Server
#### docker-machine
> If you're developing on a Mac then Docker won't run natively, you'll be running
> a single VM with linux installed where your Docker containers run. To start the vm
> run the following first before continuing:
> ```
> $ docker-machine create -d virtualbox default
> $ eval "$(docker-machine env default)"
> ```

In a terminal `cd` into the directory you checked this project out into, then

```
$ docker-compose build && docker-compose up
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

You should be able to point your browser at the VM's url
You can find it by typing `docker-machine ip` in a terminal. Then visit http://**docker-machine ip**:8000/.
You should see an `HTTP 401 Unauthorized` page.


#### Without Docker

If you don't want to use Docker, follow these steps to set up your environment:

Install `virtualenv`:

```
pip install virtualenv
```

Create and activate a new environment:

```
virtualenv --python=python3 venv
source venv/bin/activate
```

Install dependencies:

```
pip install -r requirements/dev.txt
```

Install postgres, connect to it and run:

```
create database mtp_api;
```

By default the project uses the 'postgres' user with no password. This can be 
overridden by setting the `DB_USERNAME` and `DB_PASSWORD` environment variables
and creating a new user as follows:

```
create user <whatever> with password '<whatever else>';
alter database mtp_api owner to <whatever>;
alter user <whatever> with superuser;
```

To set up the database with sample data:

```
python manage.py migrate
python manage.py load_test_data
```

Start the dev server, listening on port 8000:

```
python manage.py runserver 8000
```

### Sample data generation
As well as the management command mentioned above (`python manage.py load_test_data`), the entire data set can also be regenerated from the Django admin tool (found at http://[api-host-domain]/admin/). Currently there are 2 scenarios:

* Random transaction – the standard scenario for integration testing and development (the `load_test_data` command does this by default)
* User testing the Cashbook – generates random uncredited transactions using offender names and locations from test NOMIS

These scenarios create a different set of test users for the client applications – see the user list in the Django admin tool.

### Translating

Update translation files with `./run.py make_messages` – you need to do this every time any translatable text is updated.

Pull updates from Transifex with ``./run.py translations --pull``. You'll need to update translation files afterwards and manually check that the merges occurred correctly.

Push latest English to Transifex with ``./run.py translations --push``. NB: you should pull updates before pushing to merge correctly.

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

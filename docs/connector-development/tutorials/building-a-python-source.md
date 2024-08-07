# Building a Python Source

## Summary

This article provides a checklist for how to create a python source. Each step in the checklist has a link to a more detailed explanation below.

## Requirements

Docker, Python, and Java with the versions listed in the [tech stack section](../../understanding-airbyte/tech-stack.md).

:::info

All the commands below assume that `python` points to a version of python &gt;3.7. On some systems, `python` points to a Python2 installation and `python3` points to Python3. If this is the case on your machine, substitute all `python` commands in this guide with `python3` . Otherwise, make sure to install Python 3 before beginning.

:::

## Checklist

### Creating a Source

* Step 1: Create the source using template
* Step 2: Build the newly generated source
* Step 3: Set up your Airbyte development environment
* Step 4: Implement `spec` \(and define the specification for the source `airbyte-integrations/connectors/source-<source-name>/spec.yaml`\)
* Step 5: Implement `check`
* Step 6: Implement `discover`
* Step 7: Implement `read`
* Step 8: Set up Connector Acceptance Tests
* Step 9: Write unit tests or integration tests
* Step 10: Update the `README.md` \(If API credentials are required to run the integration, please document how they can be obtained or link to a how-to guide.\)
* Step 11: Update the `metadata.yaml` file with accurate information about your connector. These metadata will be used to add the connector to Airbyte's connector registry.
* Step 12: Add docs \(in `docs/integrations/sources/<source-name>.md`\)

:::info
Each step of the Creating a Source checklist is explained in more detail below.
:::

:::info
All `./gradlew` commands must be run from the root of the airbyte project.
:::

### Submitting a Source to Airbyte

* If you need help with any step of the process, feel free to submit a PR with your progress and any questions you have.
* Submit a PR.
* To run integration tests, Airbyte needs access to a test account/environment. Coordinate with an Airbyte engineer \(via the PR\) to add test credentials so that we can run tests for the integration in the CI. \(We will create our own test account once you let us know what source we need to create it for.\)
* Once the config is stored in Github Secrets, edit `.github/workflows/test-command.yml` and `.github/workflows/publish-command.yml` to inject the config into the build environment.
* Edit the `airbyte/tools/bin/ci_credentials.sh` script to pull the script from the build environment and write it to `secrets/config.json` during the build.

:::info
If you have a question about a step the Submitting a Source to Airbyte checklist include it in your PR or ask it on [#help-connector-development channel on Slack](https://airbytehq.slack.com/archives/C027KKE4BCZ).
:::

## Explaining Each Step

### Step 1: Create the source using template

Airbyte provides a code generator which bootstraps the scaffolding for our connector.

```bash
$ cd airbyte-integrations/connector-templates/generator # assumes you are starting from the root of the Airbyte project.
$ ./generate.sh
```

Select the `python` template and then input the name of your connector. For this walk through we will refer to our source as `example-python`

### Step 2: Install the newly generated source

Install the source by running:

```bash
cd airbyte-integrations/connectors/source-<name>
poetry install
```

This step sets up the initial python environment. 

### Step 3: Set up your Airbyte development environment

The generator creates a file `source_<source_name>/source.py`. This will be where you implement the logic for your source. The templated `source.py` contains extensive comments explaining each method that needs to be implemented. Briefly here is an overview of each of these methods.

1. `spec`: declares the user-provided credentials or configuration needed to run the connector
2. `check`: tests if with the user-provided configuration the connector can connect with the underlying data source.
3. `discover`: declares the different streams of data that this connector can output
4. `read`: reads data from the underlying data source \(The stock ticker API\)

#### Dependencies

Python dependencies for your source should be declared in `airbyte-integrations/connectors/source-<source-name>/setup.py` in the `install_requires` field. You will notice that a couple of Airbyte dependencies are already declared there. Do not remove these; they give your source access to the helper interface that is provided by the generator.

You may notice that there is a `requirements.txt` in your source's directory as well. Do not touch this. It is autogenerated and used to provide Airbyte dependencies. All your dependencies should be declared in `setup.py`.

#### Development Environment

The commands we ran above created a virtual environment for your source. If you want your IDE to auto complete and resolve dependencies properly, point it at the virtual env `airbyte-integrations/connectors/source-<source-name>/.venv`. Also anytime you change the dependencies in the `setup.py` make sure to re-run the build command. The build system will handle installing all dependencies in the `setup.py` into the virtual environment.

Pretty much all it takes to create a source is to implement the `Source` interface. The template fills in a lot of information for you and has extensive docstrings describing what you need to do to implement each method. The next 4 steps are just implementing that interface.

:::info
All logging should be done through the `logger` object passed into each method. Otherwise, logs will not be shown in the Airbyte UI.
:::

#### Iterating on your implementation

Everyone develops differently but here are 3 ways that we recommend iterating on a source. Consider using whichever one matches your style.

**Run the source using python**

You'll notice in your source's directory that there is a python file called `main.py`. This file exists as convenience for development. You can call it from within the virtual environment mentioned above `. ./.venv/bin/activate` to test out that your source works.

```bash
# from airbyte-integrations/connectors/source-<source-name>
poetry run source-<source-name> spec
poetry run source-<source-name> check --config secrets/config.json
poetry run source-<source-name> discover --config secrets/config.json
poetry run source-<source-name> read --config secrets/config.json --catalog sample_files/configured_catalog.json
```

The nice thing about this approach is that you can iterate completely within in python. The downside is that you are not quite running your source as it will actually be run by Airbyte. Specifically you're not running it from within the docker container that will house it.


**Build the source docker image**

You have to build a docker image for your connector if you want to run your source exactly as it will be run by Airbyte.

**Option A: Building the docker image with `airbyte-ci`**

This is the preferred method for building and testing connectors.

If you want to open source your connector we encourage you to use our [`airbyte-ci`](https://github.com/airbytehq/airbyte/blob/master/airbyte-ci/connectors/pipelines/README.md) tool to build your connector. 
It will not use a Dockerfile but will build the connector image from our [base image](https://github.com/airbytehq/airbyte/blob/master/airbyte-ci/connectors/base_images/README.md) and use our internal build logic to build an image from your Python connector code.

Running `airbyte-ci connectors --name source-<source-name> build` will build your connector image.
Once the command is done, you will find your connector image in your local docker host: `airbyte/source-<source-name>:dev`.



**Option B: Building the docker image with a Dockerfile**

If you don't want to rely on `airbyte-ci` to build your connector, you can build the docker image using your own Dockerfile. This method is not preferred, and is not supported for certified connectors.

Create a `Dockerfile` in the root of your connector directory. The `Dockerfile` should look something like this:

```Dockerfile

FROM airbyte/python-connector-base:1.1.0

COPY . ./airbyte/integration_code
RUN pip install ./airbyte/integration_code

# The entrypoint and default env vars are already set in the base image
# ENV AIRBYTE_ENTRYPOINT "python /airbyte/integration_code/main.py"
# ENTRYPOINT ["python", "/airbyte/integration_code/main.py"]
```

Please use this as an example. This is not optimized.

Build your image:
```bash
docker build . -t airbyte/source-example-python:dev
```

**Run the source docker image**

```bash
docker run --rm airbyte/source-example-python:dev spec
docker run --rm -v $(pwd)/secrets:/secrets airbyte/source-example-python:dev check --config /secrets/config.json
docker run --rm -v $(pwd)/secrets:/secrets airbyte/source-example-python:dev discover --config /secrets/config.json
docker run --rm -v $(pwd)/secrets:/secrets -v $(pwd)/sample_files:/sample_files airbyte/source-example-python:dev read --config /secrets/config.json --catalog /sample_files/configured_catalog.json
```

:::info
Each time you make a change to your implementation you need to re-build the connector image. This ensures the new python code is added into the docker container.
:::

The nice thing about this approach is that you are running your source exactly as it will be run by Airbyte. The tradeoff is that iteration is slightly slower, because you need to re-build the connector between each change.

**Detailed Debug Messages**

During development of your connector, you can enable the printing of detailed debug information during a sync by specifying the `--debug` flag. This will allow you to get a better picture of what is happening during each step of your sync.

```bash
poetry run source-<source-name> read --config secrets/config.json --catalog sample_files/configured_catalog.json --debug
```

In addition to the preset CDK debug statements, you can also emit custom debug information from your connector by introducing your own debug statements:

```python
self.logger.debug(
    "your debug message here",
    extra={
        "debug_field": self.value,
        "custom_field": your_object.field
    }
)
```

**TDD using acceptance tests & integration tests**

Airbyte provides an acceptance test suite that is run against every source. The objective of these tests is to provide some "free" tests that can sanity check that the basic functionality of the source works. One approach to developing your connector is to simply run the tests between each change and use the feedback from them to guide your development.

If you want to try out this approach, check out Step 8 which describes what you need to do to set up the standard tests for your source.

The nice thing about this approach is that you are running your source exactly as Airbyte will run it in the CI. The downside is that the tests do not run very quickly.

### Step 4: Implement `spec`

Each source contains a specification that describes what inputs it needs in order for it to pull data. This file can be found in `airbyte-integrations/connectors/source-<source-name>/spec.yaml`. This is a good place to start when developing your source. Using JsonSchema define what the inputs are \(e.g. username and password\). Here's [an example](https://github.com/airbytehq/airbyte/blob/master/airbyte-integrations/connectors/source-stripe/source_stripe/spec.yaml) of what the `spec.yaml` looks like for the stripe source.

For more details on what the spec is, you can read about the Airbyte Protocol [here](../../understanding-airbyte/airbyte-protocol.md).

The generated code that Airbyte provides, handles implementing the `spec` method for you. It assumes that there will be a file called `spec.yaml` in the same directory as `source.py`. If you have declared the necessary JsonSchema in `spec.yaml` you should be done with this step.

### Step 5: Implement `check`

As described in the template code, this method takes in a json object called config that has the values described in the `spec.yaml` filled in. In other words if the `spec.yaml` said that the source requires a `username` and `password` the config object might be `{ "username": "airbyte", "password": "password123" }`. It returns a json object that reports, given the credentials in the config, whether we were able to connect to the source. For example, with the given credentials could the source connect to the database server.

While developing, we recommend storing this object in `secrets/config.json`. The `secrets` directory is gitignored by default.

### Step 6: Implement `discover`

As described in the template code, this method takes in the same config object as `check`. It then returns a json object called a `catalog` that describes what data is available and metadata on what options are available for how to replicate it.

For a brief overview on the catalog check out [Beginner's Guide to the Airbyte Catalog](../../understanding-airbyte/beginners-guide-to-catalog.md).

### Step 7: Implement `read`

As described in the template code, this method takes in the same config object as the previous methods. It also takes in a "configured catalog". This object wraps the catalog emitted by the `discover` step and includes configuration on how the data should be replicated. For a brief overview on the configured catalog check out [Beginner's Guide to the Airbyte Catalog](../../understanding-airbyte/beginners-guide-to-catalog.md). It then returns a generator which returns each record in the stream.

### Step 8: Set up Connector Acceptance Tests (CATs)

The Connector Acceptance Tests are a set of tests that run against all sources. These tests are run in the Airbyte CI to prevent regressions. They also can help you sanity check that your source works as expected. The following [article](../testing-connectors/connector-acceptance-tests-reference.md) explains Connector Acceptance Tests and how to run them.

You can run the tests using [`airbyte-ci`](https://github.com/airbytehq/airbyte/blob/master/airbyte-ci/connectors/pipelines/README.md):
`airbyte-ci connectors --name source-<source-name> test --only-step=acceptance`

:::info
In some rare cases we make exceptions and allow a source to not need to pass all the standard tests. If for some reason you think your source cannot reasonably pass one of the tests cases, reach out to us on github or slack, and we can determine whether there's a change we can make so that the test will pass or if we should skip that test for your source.
:::

### Step 9: Write unit tests and/or integration tests

The connector acceptance tests are meant to cover the basic functionality of a source. Think of it as the bare minimum required for us to add a source to Airbyte. In case you need to test additional functionality of your source, write unit or integration tests.

#### Unit Tests

Add any relevant unit tests to the `tests/unit_tests` directory. Unit tests should _not_ depend on any secrets.

You can run the tests using `poetry run pytest tests/unit_tests`

#### Integration Tests

Place any integration tests in the `integration_tests` directory such that they can be [discovered by pytest](https://docs.pytest.org/en/6.2.x/goodpractices.html#conventions-for-python-test-discovery).

You can run the tests using `poetry run pytest tests/integration_tests`

### Step 10: Update the `README.md`

The template fills in most of the information for the readme for you. Unless there is a special case, the only piece of information you need to add is how one can get the credentials required to run the source. e.g. Where one can find the relevant API key, etc.

### Step 11: Add the connector to the API/UI
There are multiple ways to use the connector you have built.

If you are self hosting Airbyte (OSS) you are able to use the Custom Connector feature. This feature allows you to run any Docker container that implements the Airbye protocol. You can read more about it [here](https://docs.airbyte.com/integrations/custom-connectors/).

If you are using Airbyte Cloud (or OSS), you can submit a PR to add your connector to the Airbyte repository. Once the PR is merged, the connector will be available to all Airbyte Cloud users. You can read more about it [here](https://docs.airbyte.com/contributing-to-airbyte/submit-new-connector).

Note that when submitting an Airbyte connector, you will need to ensure that
1. The connector passes the CAT suite. See [Set up Connector Acceptance Tests](#step-8-set-up-connector-acceptance-tests-\(cats\)).
2. The metadata.yaml file (created by our generator) is filed out and valid. See [Connector Metadata File](https://docs.airbyte.com/connector-development/connector-metadata-file).
3. You have created appropriate documentation for the connector. See [Add docs](#step-12-add-docs).


### Step 12: Add docs

Each connector has its own documentation page. By convention, that page should have the following path: in `docs/integrations/sources/<source-name>.md`. For the documentation to get packaged with the docs, make sure to add a link to it in `docs/SUMMARY.md`. You can pattern match doing that from existing connectors.

## Related tutorials
For additional examples of how to use the Python CDK to build an Airbyte source connector, see the following tutorials:
- [Python CDK Speedrun: Creating a Source](https://docs.airbyte.com/connector-development/tutorials/cdk-speedrun)
- [Build a connector to extract data from the Webflow API](https://airbyte.com/tutorials/extract-data-from-the-webflow-api)

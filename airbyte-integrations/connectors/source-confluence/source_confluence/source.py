#
# Copyright (c) 2023 Airbyte, Inc., all rights reserved.
#

import logging
from abc import ABC
from base64 import b64encode
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple
from urllib.parse import urlparse, parse_qs

import requests
from airbyte_cdk.sources import AbstractSource
from airbyte_cdk.sources.streams import Stream
from airbyte_cdk.sources.streams.http import HttpStream
from airbyte_cdk.sources.streams.http.requests_native_auth import TokenAuthenticator
from airbyte_cdk.sources.utils.transform import TransformConfig, TypeTransformer
from datetime import datetime

logger = logging.getLogger("airbyte")


def convert_date(date_string):
    # Parse the date string into a datetime object
    date_object = datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S.%fZ")

    # Format the datetime object into the desired string format
    formatted_date = date_object.strftime("%Y-%m-%d %H:%M")

    return formatted_date

def get_nested_field(d, keys, default=None):
    """
    Fetches a deeply nested field from a dictionary.

    Parameters:
    - d: The dictionary from which to fetch the value.
    - keys: A list of keys representing the path to the nested field.
    - default: The default value to return if the path does not exist.

    Returns:
    The value at the nested field if it exists, otherwise `default`.
    """
    assert isinstance(keys, list), "keys must be provided as a list"

    for key in keys:
        try:
            d = d[key]
        except (KeyError, TypeError):
            return default
    return d


def set_nested_field(d, keys, value):
    """
    Sets a value in a deeply nested dictionary, creating intermediate dictionaries if necessary.

    Parameters:
    - d: The dictionary in which to set the value.
    - keys: A list of keys representing the path where the value should be set.
    - value: The value to set at the specified path.
    """
    assert isinstance(keys, list) and keys, "keys must be provided as a non-empty list"

    for key in keys[:-1]:  # Iterate over all but the last key
        d = d.setdefault(key, {})  # Create a new dictionary if the key does not exist

    d[keys[-1]] = value  # Set the value at the final key


# Basic full refresh stream
class ConfluenceStream(HttpStream, ABC):
    url_base = "https://{}/wiki/rest/api/"
    primary_key = "id"
    limit = 50
    start = 0
    expand = []
    transformer: TypeTransformer = TypeTransformer(
        TransformConfig.DefaultSchemaNormalization
    )

    def __init__(self, config: Dict):
        super().__init__(authenticator=config["authenticator"])
        self.config = config
        self.url_base = self.url_base.format(config["domain_name"])

    def next_page_token(
        self, response: requests.Response
    ) -> Optional[Mapping[str, Any]]:
        json_response = response.json()
        links = json_response.get("_links")
        next_link = links.get("next")
        if next_link:
            self.start += self.limit
            return {"start": self.start}

    def request_params(
        self,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> MutableMapping[str, Any]:
        params = {"limit": self.limit, "expand": ",".join(self.expand)}
        if next_page_token:
            params.update({"start": next_page_token["start"]})
        return params

    def parse_response(
        self, response: requests.Response, **kwargs
    ) -> Iterable[Mapping]:
        json_response = response.json()
        records = json_response.get("results", [])
        yield from records

    def path(
        self,
        stream_state: Mapping[str, Any] = None,
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> str:
        return self.api_name


class BaseContentStream(ConfluenceStream, ABC):
    api_name = "content"
    expand = [
        "history",
        "history.lastUpdated",
        "history.previousVersion",
        "history.contributors",
        "restrictions.read.restrictions.user",
        "version",
        "descendants.comment",
        "body",
        "body.storage",
        "body.view",
    ]
    limit = 25
    content_type = None

    def get_updated_state(
        self,
        current_stream_state: MutableMapping[str, Any],
        latest_record: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        latest_record_state = get_nested_field(latest_record, self.cursor_field)
        if stream_state := get_nested_field(current_stream_state, self.cursor_field):
            set_nested_field(
                current_stream_state,
                self.cursor_field,
                max(stream_state, latest_record_state),
            )
            return current_stream_state
        newState = {}
        set_nested_field(newState, self.cursor_field, latest_record_state)
        return newState

    def next_page_token(
        self, response: requests.Response
    ) -> Optional[Mapping[str, Any]]:
        json_response = response.json()
        links = json_response.get("_links")
        next_link = links.get("next")
        logger.info(f"Next link: {next_link}")
        if next_link:
            parsed_url = urlparse(next_link)
            query_params = parse_qs(parsed_url.query)

            # Convert query parameters to dict with single values (instead of lists)
            return {k: v[0] if len(v) == 1 else v for k, v in query_params.items()}

    def request_params(
        self,
        stream_state: Mapping[str, Any],
        stream_slice: Mapping[str, any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> MutableMapping[str, Any]:
        params = {
            "limit": self.limit,
            "expand": ",".join(self.expand),
            "cql": f"type={self.content_type}",
        }

        if stream_state:
            cursor = get_nested_field(stream_state, self.cursor_field)
            if cursor:
                params["cql"] = f"{params['cql']} AND lastmodified > \"{convert_date(cursor)}\""

        if "cql" in self.config:
            params["cql"] = f"{params['cql']} AND {self.config['cql']}"

        if next_page_token:
            return next_page_token
        return params

    def parse_response(
        self, response: requests.Response, **kwargs
    ) -> Iterable[Mapping]:
        json_response = response.json()
        records = json_response.get("results", [])
        yield from records

    def path(
        self,
        stream_state: Mapping[str, Any] = None,
        stream_slice: Mapping[str, Any] = None,
        next_page_token: Mapping[str, Any] = None,
    ) -> str:
        return self.api_name + "/search"


class Pages(BaseContentStream):
    """
    API documentation: https://developer.atlassian.com/cloud/confluence/rest/api-group-content/#api-wiki-rest-api-content-get
    """

    cursor_field = ["history", "lastUpdated", "when"]
    content_type = "page"


class BlogPosts(BaseContentStream):
    """
    API documentation: https://developer.atlassian.com/cloud/confluence/rest/api-group-content/#api-wiki-rest-api-content-get
    """

    content_type = "blogpost"


class Space(ConfluenceStream):
    """
    API documentation: https://developer.atlassian.com/cloud/confluence/rest/api-group-space/#api-wiki-rest-api-space-get
    """

    api_name = "space"
    expand = ["permissions", "icon", "description.plain", "description.view"]


class Group(ConfluenceStream):
    """
    API documentation: https://developer.atlassian.com/cloud/confluence/rest/api-group-group/#api-wiki-rest-api-group-get
    """

    api_name = "group"


class Audit(ConfluenceStream):
    """
    API documentation: https://developer.atlassian.com/cloud/confluence/rest/api-group-audit/#api-wiki-rest-api-audit-get
    """

    primary_key = "author"
    api_name = "audit"
    limit = 1000


# Source
class HttpBasicAuthenticator(TokenAuthenticator):
    def __init__(self, email: str, token: str, auth_method: str = "Basic", **kwargs):
        auth_string = f"{email}:{token}".encode("utf8")
        b64_encoded = b64encode(auth_string).decode("utf8")
        super().__init__(token=b64_encoded, auth_method=auth_method, **kwargs)


class SourceConfluence(AbstractSource):
    def check_connection(self, logger, config) -> Tuple[bool, any]:
        auth = HttpBasicAuthenticator(
            config["email"], config["api_token"], auth_method="Basic"
        ).get_auth_header()
        url = f"https://{config['domain_name']}/wiki/rest/api/space"
        try:
            response = requests.get(url, headers=auth)
            response.raise_for_status()
            return True, None
        except requests.exceptions.RequestException as e:
            return False, e

    def account_plan_validation(self, config, auth):
        # stream Audit requires Premium or Standard Plan
        url = f"https://{config['domain_name']}/wiki/rest/api/audit?limit=1"
        is_premium_or_standard_plan = False
        try:
            response = requests.get(url, headers=auth.get_auth_header())
            response.raise_for_status()
            is_premium_or_standard_plan = True
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"An exception occurred while trying to access Audit stream: {str(e)}. Skipping this stream."
            )
        finally:
            return is_premium_or_standard_plan

    def streams(self, config: Mapping[str, Any]) -> List[Stream]:
        auth = HttpBasicAuthenticator(
            config["email"], config["api_token"], auth_method="Basic"
        )
        config["authenticator"] = auth
        streams = [Pages(config), BlogPosts(config), Space(config), Group(config)]
        if self.account_plan_validation(config, auth):
            streams.append(Audit(config))
        return streams

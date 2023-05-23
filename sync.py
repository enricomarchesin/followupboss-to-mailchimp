#!/usr/bin/env python
import hashlib
from pathlib import Path
from typing import Tuple

import httpx
import polars as pl
from dynaconf import Dynaconf, Validator
from dynaconf.utils.boxing import DynaBox

SETTINGS = Dynaconf(
    environments=True,
    envvar_prefix=False,
    merge_enabled=True,
    load_dotenv=True,
    settings_file="settings.yaml",
    secrets=".secrets.yaml",
    validators=[
        Validator("followupboss_api_key", must_exist=True),
        Validator("followupboss_api_url", must_exist=True),
        Validator("followupboss_limit", default=100),
        Validator("mailchimp_api_key", must_exist=True),
        Validator("mailchimp_api_url", must_exist=True),
        Validator("mailchimp_limit", default=1000),
        Validator("mailchimp_error_tag", default="Mailchimp API Error"),
    ],
)
FUB_EXCLUDE = set(SETTINGS.followupboss_exclude_tags)
FUB_EXCLUDE.add(SETTINGS.mailchimp_error_tag)


def clean_mailchimp_member(member: dict):
    member["email_address"] = member["email_address"].lower()
    return member


def shuold_include_fub_person(person: dict):
    return FUB_EXCLUDE.isdisjoint(person["tags"])


def get_followupboss_people() -> list[dict]:
    fub_people = []

    fub_auth = (SETTINGS.followupboss_api_key, "")
    with httpx.Client(base_url=SETTINGS.followupboss_api_url, auth=fub_auth) as fub_client:
        r = fub_client.get(
            "/people",
            params={
                "sort": "created",
                "limit": SETTINGS.followupboss_limit,
                "offset": 0,
                "fields": ",".join(
                    [
                        "id",
                        "name",
                        "tags",
                        "emails",
                    ]
                ),
            },
        )

        while True:
            r.raise_for_status()

            fub_people += [p for p in r.json()["people"] if shuold_include_fub_person(p)]

            metadata = r.json().get("_metadata", {})
            next_link = metadata.get("nextLink")
            if next_link is None:
                break

            r = fub_client.get(next_link)

    return fub_people


def get_mailchimp_members_and_audience_id(list: str = None) -> Tuple[list[dict], str]:
    mc_members = []

    mc_headers = {"Authorization": f"Bearer {SETTINGS.mailchimp_api_key}"}
    with httpx.Client(base_url=SETTINGS.mailchimp_api_url, headers=mc_headers, timeout=30.0) as mc_client:
        r = mc_client.get(
            "/lists",
            params={
                "sort_field": "date_created",
                "sort_dir": "DESC",
                "count": SETTINGS.mailchimp_limit,
                "offset": 0,
                "fields": ",".join(
                    [
                        f"lists.{f}"
                        for f in [
                            "id",
                            "name",
                        ]
                    ]
                ),
            },
        )
        r.raise_for_status()

        audiences = [l for l in r.json()["lists"]]
        if not audiences:
            raise Exception("No audience/list defined yet in Mailchimp")
        if SETTINGS.get("mc_audience"):
            audiences = [l for l in audiences if l["name"] == SETTINGS.mailchimp_audience]
            if not audiences:
                raise Exception("Cannot find audience/list: %s", SETTINGS.mailchimp_audience)
            if len(audiences) > 1:
                raise Exception("Ambiguous audience/list name: %s", SETTINGS.mailchimp_audience)
        audience = DynaBox(audiences[0])
        print("Target Mailchimp audience:", audience.name, f"(id: {audience.id})")

        offset = 0
        while True:
            r = mc_client.get(
                f"/lists/{audience.id}/members",
                params={
                    "sort_field": "timestamp_signup",
                    "sort_dir": "ASC",
                    "count": SETTINGS.mailchimp_limit,
                    "offset": offset,
                    "fields": ",".join(
                        [
                            f"members.{f}"
                            for f in [
                                "email_address",
                                "status",
                                "tags",
                            ]
                        ]
                        + ["total_items"]
                    ),
                },
            )
            r.raise_for_status()

            mc_members += [clean_mailchimp_member(m) for m in r.json()["members"]]

            offset += SETTINGS.mailchimp_limit
            if offset >= r.json()["total_items"]:
                break

    return mc_members, audience.id


def update_followup_person_tags(person_id: str, tags: list[str]):
    fub_auth = (SETTINGS.followupboss_api_key, "")
    with httpx.Client(base_url=SETTINGS.followupboss_api_url, auth=fub_auth) as fub_client:
        r = fub_client.put(
            f"/people/{person_id}",
            json={
                "tags": tags,
            },
        )
        r.raise_for_status()


def update_mailchimp_member_tags(audience_id: str, email: str, tags: list[str]):
    email_hash = hashlib.md5(email.encode("utf-8")).hexdigest()

    mc_headers = {"Authorization": f"Bearer {SETTINGS.mailchimp_api_key}"}
    with httpx.Client(base_url=SETTINGS.mailchimp_api_url, headers=mc_headers) as mc_client:
        r = mc_client.post(
            f"/lists/{audience_id}/members/{email_hash}/tags",
            json={
                "tags": [{"name":t, "status":"active"} for t in tags],
            },
        )
        r.raise_for_status()


def add_mailchimp_member(audience_id: str, email: str, tags: list[str]):
    email_hash = hashlib.md5(email.encode("utf-8")).hexdigest()

    mc_headers = {"Authorization": f"Bearer {SETTINGS.mailchimp_api_key}"}
    with httpx.Client(base_url=SETTINGS.mailchimp_api_url, headers=mc_headers) as mc_client:
        r = mc_client.post(
            f"/lists/{audience_id}/members",
            json={
                "email_address": email,
                "status": "subscribed",
                "tags": tags,
            },
        )
        print(r.status_code, r.json())
        r.raise_for_status()

if __name__ == "__main__":
    fub_file = Path("followupboss.parquet")
    if fub_file.exists():
        fub_people_df = pl.read_parquet(fub_file)
    else:
        fub_people = get_followupboss_people()
        print("FUB people fetched:", len(fub_people))
        fub_people_df = pl.from_dicts(fub_people)
        fub_people_df.write_parquet(fub_file)
    # print("fub_people_df:", fub_people_df.shape)
    # print(fub_people_df.head())

    mc_file = Path("mailchimp.parquet")
    if mc_file.exists():
        mc_members_df = pl.read_parquet(mc_file)
        mc_audience_id = mc_members_df.audience_id.unique()[0]
    else:
        mc_members, mc_audience_id = get_mailchimp_members_and_audience_id()
        print("Mailchimp members fetched:", len(mc_members), f"(audience id: {mc_audience_id})")
        mc_members_df = pl.from_dicts(mc_members)
        mc_members_df["audience_id"] = [mc_audience_id] * len(mc_members_df)
        mc_members_df.write_parquet(mc_file)
    # print("mc_members_df:", fub_people_df.shape)
    # print(mc_members_df.head())

    failures = 0
    new_members = 0
    updated_members = 0
    already_ok = 0
    for fub_id, fub_name, fub_tags, fub_emails in fub_people_df.rows():
        if not fub_emails:
            continue

        for fub_email in [em["value"].lower() for em in fub_emails]:
            matching_mc_members = mc_members_df[mc_members_df.email_address == fub_email]
            try:
                if matching_mc_members.is_empty():
                    add_mailchimp_member(mc_audience_id, fub_email, fub_tags)
                    new_members += 1
                else:
                    mc_email, mc_status, mc_tags, member_audience_id = matching_mc_members.rows()[0]
                    mc_tags = [t["name"] for t in mc_tags] if mc_tags else []
                    fub_tags_missing_in_mailchimp = set(fub_tags) - set(mc_tags)
                    if fub_tags_missing_in_mailchimp:
                        update_mailchimp_member_tags(member_audience_id, fub_email, fub_tags)
                        updated_members += 1
                    else:
                        already_ok += 1
            except Exception as e:
                failures += 1
                print("!!!!!!", e)
                update_followup_person_tags(fub_id, fub_tags + [SETTINGS.mailchimp_error_tag])

    print("Already ok:", already_ok)
    print("Updated members:", updated_members)
    print("New members:", new_members)
    print("Failures:", failures)

    mc_file.unlink()
    fub_file.unlink()

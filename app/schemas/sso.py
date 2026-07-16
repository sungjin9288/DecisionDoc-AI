"""Strict request models for SSO configuration updates."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictUpdate(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


_Domain = Annotated[str, Field(max_length=253)]


class LDAPConfigUpdate(_StrictUpdate):
    server_url: str = Field(default="", max_length=2048)
    bind_dn: str = Field(default="", max_length=4096)
    bind_password: str = Field(default="", max_length=16384)
    base_dn: str = Field(default="", max_length=4096)
    user_search_filter: str = Field(default="", max_length=4096)
    group_search_base: str = Field(default="", max_length=4096)
    admin_group: str = Field(default="", max_length=4096)
    member_group: str = Field(default="", max_length=4096)
    viewer_group: str = Field(default="", max_length=4096)
    tls: bool = False


class SAMLConfigUpdate(_StrictUpdate):
    idp_entity_id: str = Field(default="", max_length=2048)
    idp_sso_url: str = Field(default="", max_length=2048)
    idp_certificate: str = Field(default="", max_length=65536)
    sp_entity_id: str = Field(default="", max_length=2048)
    sp_acs_url: str = Field(default="", max_length=2048)
    sp_private_key: str = Field(default="", max_length=65536)
    sp_certificate: str = Field(default="", max_length=65536)
    name_id_format: str = Field(default="", max_length=2048)
    attribute_username: str = Field(default="", max_length=256)
    attribute_display_name: str = Field(default="", max_length=256)
    attribute_role: str = Field(default="", max_length=256)


class GCloudConfigUpdate(_StrictUpdate):
    client_id: str = Field(default="", max_length=4096)
    client_secret: str = Field(default="", max_length=16384)
    hd: str = Field(default="", max_length=253)
    allowed_domains: list[_Domain] = Field(default_factory=list, max_length=50)
    default_role: Literal["admin", "member", "viewer"] = "member"


class OAuth2ConfigUpdate(_StrictUpdate):
    client_id: str = Field(default="", max_length=4096)
    client_secret: str = Field(default="", max_length=16384)
    auth_url: str = Field(default="", max_length=2048)
    token_url: str = Field(default="", max_length=2048)
    userinfo_url: str = Field(default="", max_length=2048)
    scope: str = Field(default="", max_length=2048)
    redirect_uri: str = Field(default="", max_length=2048)
    username_claim: str = Field(default="", max_length=256)
    display_name_claim: str = Field(default="", max_length=256)
    default_role: Literal["admin", "member", "viewer"] = "member"


class UpdateSSOConfigRequest(_StrictUpdate):
    provider: Literal["disabled", "ldap", "saml", "gcloud", "oauth2"] | None = None
    ldap: LDAPConfigUpdate | None = None
    saml: SAMLConfigUpdate | None = None
    gcloud: GCloudConfigUpdate | None = None
    oauth2: OAuth2ConfigUpdate | None = None


class LDAPLoginRequest(_StrictUpdate):
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=4096)

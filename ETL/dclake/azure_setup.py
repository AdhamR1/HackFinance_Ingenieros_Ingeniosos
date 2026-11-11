"""Create the Azure Data Lake Gen2 of the project from here: python -m dclake azure-setup

Signs in through the browser (no key is typed or shown), picks the subscription (the
"Azure for Students" one if there are several), and creates, or reuses if they exist:
  - resource group   azure.resource_group (config.yaml)
  - storage account  <azure.account_prefix><6 hex>, StorageV2, Standard_LRS, hierarchical
                     namespace (= ADLS Gen2), HTTPS + TLS 1.2 only, no public blob access
  - container        AZURE_STORAGE_CONTAINER (default dclake)
The first region of azure.regions that the subscription allows is used (student subscriptions
restrict regions by policy). Finally it writes AZURE_STORAGE_ACCOUNT, AZURE_STORAGE_CONTAINER
and a container SAS valid azure.sas_days days to .env, without printing it; `upload` then
works with no further steps. Running it again reuses everything and only renews the SAS.

Optional in .env: AZURE_TENANT_ID (directory to sign in to, needed for a personal Microsoft
account) and AZURE_SUBSCRIPTION_ID (when the account has several subscriptions).
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

ARM_SCOPE = "https://management.azure.com/.default"
DEFAULTS = {
    "resource_group": "rg-dclake-hackathon",
    "account_prefix": "stdclake",
    "regions": ["spaincentral", "francecentral", "westeurope", "northeurope", "swedencentral"],
    "sas_days": 90,
}
TAGS = {"project": "dclake", "purpose": "hackathon"}


def set_env_values(path: Path, values: dict[str, str]) -> None:
    """Set KEY=value lines in a .env file: replaces existing keys (also commented-out empty
    ones like `KEY=`), appends the rest, keeps every other line untouched."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(values)
    for i, line in enumerate(lines):
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and m.group(1) in pending:
            key = m.group(1)
            lines[i] = f"{key}={pending.pop(key)}"
    if pending:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# --- escrito por python -m dclake azure-setup ---")
        lines += [f"{k}={v}" for k, v in pending.items()]
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(path)


class _InTenant:
    """The same signed-in credential, asking for tokens of one directory (tenant)."""

    def __init__(self, cred, tenant_id: str):
        self.cred, self.tenant_id = cred, tenant_id

    def get_token(self, *scopes, **kw):
        kw["tenant_id"] = self.tenant_id
        return self.cred.get_token(*scopes, **kw)


def _credential(cfg, log):
    from azure.identity import InteractiveBrowserCredential

    tenant = cfg.secret("AZURE_TENANT_ID") or "organizations"
    log.info("Se abre el navegador para iniciar sesión en Azure (elige la cuenta de estudiante)")
    cred = InteractiveBrowserCredential(tenant_id=tenant, additionally_allowed_tenants=["*"])
    cred.get_token(ARM_SCOPE)  # sign in now, not halfway through
    return cred


def _subscription(cred, cfg, log):
    """(subscription, credential for its tenant). Searches every directory of the account."""
    from azure.mgmt.resource.subscriptions import SubscriptionClient

    wanted = cfg.secret("AZURE_SUBSCRIPTION_ID")
    found = []
    tenants = [t.tenant_id for t in SubscriptionClient(cred).tenants.list()]
    for tid in tenants:
        tcred = _InTenant(cred, tid)
        try:
            subs = list(SubscriptionClient(tcred).subscriptions.list())
        except Exception as e:  # a directory that needs MFA or that we cannot read
            log.warning("No se pueden listar las suscripciones del directorio %s: %s", tid, e)
            continue
        found += [(s, tcred) for s in subs if str(s.state).lower().endswith("enabled")]
    if wanted:
        found = [(s, c) for s, c in found if s.subscription_id == wanted]
    if not found:
        raise RuntimeError(
            "La cuenta no tiene ninguna suscripción activa"
            + (f" con id {wanted}" if wanted else "")
            + ". ¿Están canjeados los créditos? Si entraste con una cuenta personal de Microsoft, "
            "pon AZURE_TENANT_ID en .env (Portal > Microsoft Entra ID > Id. de inquilino)."
        )
    students = [x for x in found if "student" in (x[0].display_name or "").lower()]
    if len(found) > 1 and len(students) != 1:
        names = ", ".join(f"{s.display_name} ({s.subscription_id})" for s, _ in found)
        raise RuntimeError(
            f"Hay varias suscripciones; elige una con AZURE_SUBSCRIPTION_ID: {names}"
        )
    sub, tcred = students[0] if len(found) > 1 else found[0]
    log.info("Suscripción: %s (%s)", sub.display_name, sub.subscription_id)
    return sub, tcred


def _prop(obj, name):
    """Model attribute, flattened or under .properties (the SDK models do both)."""
    v = getattr(obj, name, None)
    return v if v is not None else getattr(getattr(obj, "properties", None), name, None)


def _disallowed(e: Exception) -> bool:
    text = f"{getattr(e, 'error', '')} {e}"
    return any(
        k in text
        for k in (
            "RequestDisallowedByPolicy",
            "LocationNotAvailable",
            "NoRegisteredProvider",
            "SkuNotAvailable",
            "disallowed",
            "not available",
        )
    )


def _ensure_account(storage, resources, az, log):
    """Reuse the project's account in the resource group, or create it in the first allowed
    region. Returns the account object."""
    from azure.core.exceptions import ResourceNotFoundError
    from azure.mgmt.storage import models as m

    rg = az["resource_group"]
    try:
        group = resources.resource_groups.get(rg)
    except ResourceNotFoundError:
        group = None
    if group is not None:
        for acct in storage.storage_accounts.list_by_resource_group(rg):
            if acct.name.startswith(az["account_prefix"]):
                log.info("Se reutiliza la cuenta %s (%s)", acct.name, acct.location)
                if not _prop(acct, "is_hns_enabled"):
                    raise RuntimeError(f"{acct.name} no tiene espacio de nombres jerárquico")
                return acct

    resources.providers.register("Microsoft.Storage")
    for _ in range(5):
        name = az["account_prefix"] + secrets.token_hex(3)
        ok = storage.storage_accounts.check_name_availability(
            m.StorageAccountCheckNameAvailabilityParameters(
                name=name, type="Microsoft.Storage/storageAccounts"
            )
        )
        if ok.name_available:
            break
    else:
        raise RuntimeError("No se encontró un nombre libre para la cuenta de almacenamiento")

    errors = {}
    for region in az["regions"]:
        try:
            if group is None:
                group = resources.resource_groups.create_or_update(
                    rg, {"location": region, "tags": TAGS}
                )
                log.info("Creado el grupo de recursos %s (%s)", rg, region)
            log.info("Creando la cuenta %s en %s (1-2 min)...", name, region)
            params = m.StorageAccountCreateParameters(
                sku=m.Sku(name="Standard_LRS"),
                kind="StorageV2",
                location=region,
                tags=TAGS,
                properties=m.StorageAccountPropertiesCreateParameters(
                    is_hns_enabled=True,
                    access_tier="Hot",
                    enable_https_traffic_only=True,
                    minimum_tls_version="TLS1_2",
                    allow_blob_public_access=False,
                    allow_shared_key_access=True,  # needed to sign the SAS
                ),
            )
            acct = storage.storage_accounts.begin_create(rg, name, params).result()
            log.info("Creada la cuenta %s en %s", acct.name, acct.location)
            return acct
        except Exception as e:
            if not _disallowed(e):
                raise
            errors[region] = str(e).splitlines()[0][:160]
            log.info("Región %s no permitida en esta suscripción; se prueba la siguiente", region)
    raise RuntimeError(f"Ninguna región de azure.regions está permitida: {errors}")


def azure_setup(cfg, log) -> str:
    """Create or reuse the lake and write its connection to .env. Returns the account name."""
    from azure.mgmt.resource.resources import ResourceManagementClient
    from azure.mgmt.storage import StorageManagementClient
    from azure.storage.filedatalake import FileSystemSasPermissions, generate_file_system_sas

    az = {**DEFAULTS, **(cfg.get("azure") or {})}
    container = cfg.secret("AZURE_STORAGE_CONTAINER") or "dclake"
    cred = _credential(cfg, log)
    sub, tcred = _subscription(cred, cfg, log)
    storage = StorageManagementClient(tcred, sub.subscription_id)
    resources = ResourceManagementClient(tcred, sub.subscription_id)

    acct = _ensure_account(storage, resources, az, log)
    rg = az["resource_group"]
    storage.blob_containers.create(rg, acct.name, container, {})  # PUT: no-op if it exists
    log.info("Contenedor %s listo", container)

    # .keys is the dict-like Model's own method (MutableMapping); the field is keys_property.
    key = storage.storage_accounts.list_keys(rg, acct.name).keys_property[0].value
    expiry = datetime.now(UTC) + timedelta(days=int(az["sas_days"]))
    sas = generate_file_system_sas(
        acct.name,
        container,
        credential=key,
        permission=FileSystemSasPermissions(
            read=True, write=True, delete=True, list=True, add=True, create=True
        ),
        expiry=expiry,
    )
    env = cfg.root / ".env"
    set_env_values(
        env,
        {
            "AZURE_STORAGE_ACCOUNT": acct.name,
            "AZURE_STORAGE_CONTAINER": container,
            "AZURE_STORAGE_SAS_TOKEN": sas,
            "AZURE_SUBSCRIPTION_ID": sub.subscription_id,
        },
    )
    log.info(
        "Data lake listo: abfss://%s@%s.dfs.core.windows.net/ (región %s). Conexión y token "
        "de acceso (caduca el %s) guardados en %s sin mostrarlos.",
        container,
        acct.name,
        acct.location,
        expiry.date(),
        env,
    )
    return acct.name

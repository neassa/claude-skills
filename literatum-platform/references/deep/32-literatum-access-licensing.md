# 32 — Literatum identity, access control and licensing (lit-2610)

Written 2026-09-27, read-only. Nothing was built or run. Every repo file went through `tools/safe_view.py`; no secret value was read. Where safe_view masked a registry key or identifier (`ac***`, `fi***`) I cite the file:line instead of the key.

**Commit read.** `$LIT_REPOS/literatum-lit-2610` was `9f8eb846e` (lit-2610) when I started and **`c9e4556e8` (detached HEAD, "Merge pull request #14313 from atypon/LIT-683617-2", 2026-09-25 20:22 +0300) when I finished** — someone moved the clone during the read. The only commit between the two touches `product/tandf/conf/tandf.props.IBM-lts.xml` and a pb2 `variableEditorController.js`; `git diff --stat` over every path cited below is empty, so all line numbers hold at both commits. Paths are relative to `atypon/`.

**Not repeated here** (read them first): note 17 §3 (read-only rules table, `AddAtyponIPsToAtyponInstitution` line by line, IP-user/group basics), note 23 (`QATestActions` impersonate, `checkSessionAccess`, AUTO_TEST_USER on the warm-up path), note 04 §8–9 (persistence read-only mechanisms and the first Patch032053 analysis), `literatum-platform/references/runtime.md`. This note **corrects** note 04 §9 in one place (§5.2 below).

**Secret-bearing lines noticed (values not read):** `product/marlin/conf/marlin.props.xml:705` (an OIDC client secret literal, next to :690/:695 already flagged in note 17 §6).

---

## 1. Identity model

### 1.1 Tables, types, relations

| Thing | Where | Facts |
|---|---|---|
| Base identity row | `GENERIC_USER` (`IdentityServiceImpl.java:32`, seq `USERID_SEQ` :33; columns `GenericUserColumns.java:5-12`: USERTYPEID, **FIELDID**, DESCRIPTION, CODE) | `IdentityImpl` registers it at `IdentityImpl.java:169,202`. Every identity type adds its own table (e.g. `IP_RANGE_USER`, `AbstractIPRangeUserColumns.java:4`; `SAML_IDP_USER`, `SAMLIdPUser.java:32`; `PERSON_COMM_CHAN`). |
| Type ids | `literatum/acs/user/column/*Columns.java`, `BasicGroupIdentityServiceImpl.java:13`, `PersonIdentityColumns.java:27` | Person 500, Domain 501, **IPRange 502**, **BasicGroup 503**, ProxyIPRange 504, Combined 505, TrustedProxy 506, **Institution 507**, Publisher 508, Society 509, Referrer 510, RemoteUser 511, WebCrawler 516, AccessToken 518, AccessTokenDomain 520, **SAMLIdP 521** (from the SQL in `DeleteOrphanSAMLIdPUser.java:16`), Consortium 525, Region 526, WebService 533, MarlinTPS1 540. |
| Relations | `USER_REL` (`IdentityRelationServiceImpl.java:29`), types in `iam/identity/model/IdentityRelation.java:26-82` | **MEMBERSHIP=1000** (user1=group, user2=member), ACTIVATION=1002, EQUIVALENCE=1003, AFFILIATION=1004, COMBINED=1005, AUTHENTICATED=1006 (masked, inferred from the sequence), PREACTIVATION=1007, DEVICE_PAIRING=1008, SUSHI=1009, IP_AFFILIATION=1010, EMAIL_AFFILIATION=1011, IDP_AFFILIATION=1012. |
| Fields (per-entity key/value bag) | `FIELD_VALUE_INFO` / `FIELD_TYPE_INFO` (`persistence/Fields.java:32-40`), keyed by the row's FIELDID | **`ENTITY_ACCESS_RIGHTS` = field type 66** (`IFieldsKey.java:102`), value `CR` = 3 (`EntityAccessRightsFlags.java:8-12`; missing field → -1 → all rights). `IP_RANGE_PATTERN` = 200 (`IFieldsKey.java:243`). |
| Predefined ids | `PredefinedUserIDs.java:14,24,38`; `AbstractEntity.java:33` | QA group **41** (`SessionData.isQA`), ALL_PERSON 60, ALL_AUTHOR 79. Ids `< 1000` are predefined and cannot be deleted (`IdentityImpl.cleanImpl:270-271` → `ACSException DELETE_PREDEFINED`; `LicenseImpl.deleteImpl:1477-1478` → `delete_predefined_content_slice`). |

### 1.2 Groups and membership

- `BasicGroupIdentityImpl` (`iam/identity/internal/BasicGroupIdentityImpl.java`, 107 lines, read fully): `cleanImpl` removes all members then activation relations (:27-31); save requires a code unless LINK_RECORD is on (:74-79). `AUTO_TEST_USER` is such a group, looked up **by code**: `IdentityServiceImpl.findByCode` → `DbUkCacheMacro.get(useCache, …, GENERIC_USER.CODE)` (:69-79; returns `null` when missing, `Error` on SQL failure).
- `IdentityMembershipServiceImpl` (:46-96): `addMember` = add MEMBERSHIP relation; `findDirectGroups(member)` = `relationService.findDirectUser1s(member, MEMBERSHIP)` filtered by class (:81-85); `removeAllGroups(user)` = `removeRelation(ANYID, user, MEMBERSHIP)` (:93-96).
- `IdentityRelationServiceImpl.findDirectUser1s` (:88-97) → all relations of user2 **through the DbColMatch cache** (`findDirectRelationsCacheAllRelations`, :169-178). The user1-side lookups deliberately bypass the cache for MEMBERSHIP (:415-420, "would flood the cache").
- **Cache semantics that matter for patches:** `CacheUtils.getSkipInTx` (`modules/cache/store/CacheUtils.java:325-335`) reads the **DB, not the cache, whenever `Transaction.exist()`**, unless the entity class is in a thread-local "force cache" set (:397-425; default empty). `AbstractDbBasic.delete()` always runs inside a transaction (:517-546). So during any `delete()` or DB patch, membership and identity lookups are fresh.

### 1.3 IP-range identities (adds to note 17 §3.3)

- `AbstractIPRangeUser` (270 lines, read fully). `setMinIP/setMaxIP` (:64-119) strip spaces, set `routingPrefix`, normalize with `"0"`/`"255"`(`"FFFF"`) fill; an unparseable max that is not dotted/colon/`*` goes through `InetAddress.getByName` (:107 — **that is a DNS lookup on arbitrary text**) and on failure logs `ERROR ACS "Invalid IP address!"` and leaves `maxIP` null.
- `validate(allowEmptyIP,isRoot)` (:170-236) messages, in order: `Missing min ip address`, `Invalid min ip address`, `Missing max ip address`, `Invalid max ip address`, `Missing Routing Prefix`, `Invalid routing prefix.`, `MinIP and MaxIP have different routing prefixes.`, `invalid.ip.range`, and for non-root callers `invalid.intranet.ip` (10/8, 172.16-31, 192.168) and `reserved.ip.range` (`reserved-ip-ranges`, `literatum.props.xml:2966`). `validateBeforeSave` (:243-247) runs with `isRoot=true` and throws a plain `Exception` carrying **only the first** message — that is the `DbException`/`Exception: Missing max ip address` seen in note 17.
- `IPRangeUser.saveImpl` (:63-89): drops a stale `IP_RANGE_PATTERN` field, saves, then **re-saves every parent group** to bump LastModified (:81-85); a `ReadOnlyException` from a read-only parent is caught and logged `ERROR ACS "failed to update DB field LastModified on its groups"` (:86-87) — a benign signature that says "this IP user sits under a read-only institution".
- `IpRangeUserServiceImpl`: request-time `get(InetAddress, useCache)` (:41-48) uses an in-memory interval tree when the full cache is on (flag at :33, key masked) else SQL `MINIP<=ip and MAXIP>=ip and ROUTINGPREFIX=…` (:50-67); `getFirst(minIp,maxIp)` (:97-109) is a fresh `Finder` on normalized min/max **plus routing prefix**; cache refresh logs `IPRangeUserCache: loaded/refreshed N IP ranges` and `IPRangeUserCache: failed to load IP range with id=` (:159-171).
- `IpRangeResolver` (116 lines, read fully): `resolve(String)` picks IPv4 vs IPv6 by `.` vs `:` (:58-67), delimiters come from two registry keys (masked, :28-29), CIDR and `*` supported; a non-range string throws `IllegalIPAddressException`.
- `IPAddressUtil.getCanonicalIP4/6` (:27-67): `InetAddress.getByName(ip).getHostAddress()` → zero-pad each segment (3 digits IPv4, 4 hex IPv6) → upper-case; on `UnknownHostException` log `ERROR ACS "Invalid IP address!"` and **return null**. This padding is why the CF WARP address is stored and searched as `104.030.132.204`.

### 1.4 Institutions and SAML identities

- `InstitutionUser.saveImpl` (:224-252): logs `ISNI name provided without ISNI ID` when inconsistent; a new institution is tagged into the Google-feed concept scheme (:241-251, a Reasoner write).
- `SAMLIdPUser` (type 521, `SAML_IDP_USER`, extends `SSOAuthnProviderImpl`): matching is in-memory over `FULL_CACHE` — entityId equal, orgId in the requested set (or any), state NORMAL, optional remote-auth flag and attribute set (:246-278). `SAMLIndividualUser` extends `SSOAuthnProfileImpl` and links to a `PersonUser`. `ShibbolethSettings` is a plain value object (entityId, orgUnitId, remoteAuthenticationEnabled, attributes).

---

## 2. Sessions and login

### 2.1 Request → session → identities

1. **`ClientIpFilter`** (`modules/servlet/ClientIpFilter.java`, 179 lines, read fully) decides the client IP, in this order: (a) origin-override header if `proxy/force-origin-ip-override` (`literatum.props.xml:1934-1935`); (b) if `proxy/useOriginalClientIP` (:1923): the internal header `F5_Source_IP` (:1932) **only when the remote address is site-local**, else `CF-Connecting-IP`; then the last IP of `X-Forwarded-For`/client-IP headers **only if the current IP is a `ProxyIPRangeUser` whose description contains one of `proxy/matchDescriptions`** (:1924-1927: "Google Web Accelerator Proxy", "Passport Analytics Proxy"); (c) if `filter/fakeIp/enabled` (:1787-1789, default false) and the source IP is an `IPRangeUser` member of **`AUTO_TEST_USER`** (`isQA`, :150-166), the fake-IP header replaces it (`INFO ACS "ClientIpFilter: fake ip … accepted"`).
2. **`SessionFilter`** (`acs/SessionFilter.java`, 286 lines, read fully): rejects logged-out/invalid sessions (:108-131); gives **shared sessions** to web crawlers, `SessionRequirement.SHARED` services and Cloudflare-verified bots (`xcf-verified-bot`, :133-167); otherwise `SessionData.from(request)` + `updateFromRequest`, or `createSessionData` when the service needs a session (:169-211). Errors: `IpBlockException` → **403** + error page; too-many-IPs → redirect `TOO_MANY_IPS_REDIRECT`; `SecureSessionCookieMismatchException` → drop JSESSIONID, redirect to the insecure host; `BlockException` → `handleBlockException`. It also arms the site read-only bypass for admin roles (:90-95).
3. **`SessionData.updateFromRequest`** (:738-748): `updateIp` → `addIpBasedIdentities` (:944-969) adds `IpRangeUserService.get(address,true)`, web crawlers, the proxy-range users and the `RegionUser` as base users with credential type **IP**; on an IP change `removeIpBasedIdentities` (:971-990) removes them. Then device, website identity, user-agent, admin HMAC cookie, country control.
4. **`SessionIdentities`** (1481 lines; read :118-236, :462-560, :891-925, :1005-1030, :1385-1415): base users → derived users by walking `USER_REL` (`collectRelatives`), skipping relatives whose relation start is in the future or whose **hold/end date has passed** (:1009-1019 — this is the *identity* hold, `Identity.getAccessHoldDate`, which `IdentityImpl` returns null for at :764-766; only subclasses implement it), plus predefined groups derived from effective licenses (:891-921, gated by a registry flag at :892), author groups, administered orgs and smart groups (`SMART_GROUP_CYCLE_LIMIT`; `ERROR ACS "SessionIdentities: Smart Groups have derived user cycle, breaking to stop infinite loop"`, :559). Shared sessions never take a PersonUser (:188-191, LIT-675166).
5. Role checks: `isQA` = predefined group 41 in session; `isTestUser` = the `AUTO_TEST_USER` group (by code) in session (:3316-3327); `isAdmin/isSuperAdmin/isDevAdmin` = `LicenseModule.getAdminLevel(session)` (AdminLicense-based, `AdminLevel.java:46-81`).

### 2.2 Local login

`SessionData.authenticate(login, password, overrideDigester, ctx)` (:2025-2109): optional lockout check (`AccountLockedException "The user Account is Locked"`), then `LoginUser.findByAuthInfo` (:229-330): empty password → `ACSException PASSWORD_NONEXIST`; email-as-username lookup if enabled (:240-252) else `findByLogin`; an invalid `LoginUser` → `LoginBlockedException` (:264-266); no digest match → `INFO "Failed login attempt for : <login>"` + `ACSException PASSWORD_MISMATCH` (:276-277); then password-rank, password-expiry (`ACSPasswordExpiredException`), passwordless comm-channel and email-verification rules (`CommunicationChannelNotVerifiedException`, `EmailNotVerifiedException`). `ACSException|NotFoundException` falls through to `authenticateRemoteUser` (:2101-2107). Each failure records a lockout attempt (:2111-2123). Concurrency of *sessions* per user: `max-concurrent-sessions` / `logout-after-max-concurrent-sessions-enabled` (`literatum.props.xml:1999-2003`; `SessionData.java:180`).

### 2.3 SSO, SAML/Shibboleth, OpenAthens, marlin ID+

- **`SsoFilter`** (112 lines, read fully): only when the SSO flag is on and the site is **not** read-only (:46); handler from `acs/sso/handler` (`AbstractSsoHandler.java:325`); `autoLogin()` → `authenticateStrongly` or `addBaseUser` with credential `Sso`; cookie-vanished → `logout` + `removeBaseUser`; any Throwable → `ERROR ACS "Error while calling sso filter!"` + RAA login-error event (:93-101).
- **SAML** (`sso/SAMLAssertionConsumerServiceAction.java`, 1506 lines; read :139-200, :670-720, grep of the rest): SAML1 POST here, SAML2 POST/Artifact in sibling actions. Flow: debug-mode short-circuit → `UserViewableException "We cannot process Institution Login at this time"` if SAML disabled → parse response (`acs/saml/show-saml-response` stores raw XML) → `SAMLBlocker.checkExistingBlock` → entityId (`INFO ACS "SAML 1.1 authentication - IdP EntityId: …"`) → resolve the individual, else `SAMLUtils.findSAMLIdpUsers(entityId, profile, orgIDs)` (`SAMLUtils.java:394-397`: first with orgIDs, then any org) → `addBaseUser(idp, Shibboleth)` (:681-685). No IdP → `WARN "SAML: no SAML IdP User associated with Entity ID … and Org IDs …"` then `SAMLFormattedException` **ATTRIBUTE_MISMATCH** or **INVALID_CERTIFICATE** (failed decryption) (:694-711) → `SAML_AUTHN_ERROR` page. Other keys: `acs/saml/capture-address`, person-creation flag (:110). Atypon-domain users are refused: `"Atypon users can only login through secure OpenID!"` (:1237-1238). Entitlements can be created from SAML attributes (:1055-1117, `"SAML: an error occurs during license creation"`). `literatum/conf/saml-attrmap.xml` and `athensconf.txt` exist (not read).
- **OpenAthens** is a SAML IdP whose attribute (URN constant at `SAMLOpenAthensAttributeHandler.java:13`) supplies the org id: the value before the first `.` is appended to `orgIDs` and set as `ORGUNIT` (:15-22, `INFO "Found attribute value=… for attribute=…"`); `isOpenAthens(idp)` = the IdP has that attribute configured (:38-46).
- **marlin Elsevier ID+ (OIDC)** — `product/marlin/src/java/com/atypon/marlin/action/user/IdUtil.java` (330), `IdCallback.java` (196), `action/sso/id/MarlinUserProcessor.java` (259): config block `marlin.props.xml:701-716` (`idPlusIntegration`: enabled=true, `clientId JBS-LOADRC`, userInfo/logout/changeOrg/**tick** URLs all on `loadRC-id.elsevier.com` **in the base file**, timeouts 5 s/10 s, scopes). `IdUtil.buildAuthRequest` (:61-108) builds the authorize redirect with callback `/callback?red_uri=…` on the primary domain (:133-146) and stores the return URL in the session; `IdCallback.execute` (:55-115) exchanges the code (`WARN "ID+ callback, code param is empty"`, `ERROR "unable to get successful response from ID+, code = … failing with status code: […]"`, `ERROR "An error occured while calling ID callback action…"`), reads userinfo, then `MarlinUserProcessor.process(claims)` (:54-…) finds/creates the PersonUser by email (:138), the CSAS customer user (:146,172), replays the TPS1 tick token (`MarlinTPS1Authenticate.authneticateTicUrlToken`, :80) and finally `authenticateStrongly(user, OAuth)` (`IdCallback.java:163`), redirecting to onboarding or the saved URL. This is the redirect that the warm-up harness follows in note 23 §1.3.

---

## 3. The access-control decision for a content request

1. **Entry.** Actions and replacers call `LicenseReplyList.getReplies(session, reqContext, ResourceRequest…)` (`publish/acs/license/LicenseReplyList.java:68-76`). Callers found: `action/TryAccess`, `seamlessaccess/SeamlessAccessAction`, `publish/action/content/ShowXml|ShowAuxFile|alternativeVersion/*`, `AccessLinkReplacer`, `ArticleLinkReplacer`, connected-products REST handlers (`TryAccessHandler`, `AccessOptionsHandler`, `DebitLicenseHandler`, `ContentAvailability`), `DefaultCartService`, `LicenseReplyServiceImpl`, `ContentRemainingUsageFetcher`, admin JSPs. `getActiveSuspendedReplies` (:79-87) is the "your subscription is suspended" variant.
2. **Collector.** A registry class (key masked, :37; default `DefaultLicenseReplyCollector`; `MappedLicenseReplyCollector` uses `PublicationToLicenseMap` and makes `SessionData.getPermissionLicenses` meaningful, :3627-3636).
3. **Which licenses are checked.** `DefaultLicenseReplyCollector.getLicensesFromSession` (:490-506) = `SessionData.getEffectiveLicenses()` (+ effective slot-seat licenses) → `getUserLicenses(effectiveOnly, useCache)` (:2948-2985): for every identity in the session (BasicGroups skipped in SPV sessions) → `LicenseService.findByUser…(id, useCache)`:
   - with `acs/redis/enabled` (`LicenseCache.java:38`; `literatum.props.xml:2933-2945`) licenses come from the **Redis user-license cache**, except for user types in `noLicenseCacheUserTypes` (`:2938`: 527,517,535,**502 (IP range)**,529,537,524,511,522) which always go to the DB cache;
   - otherwise the `DbColMatchCache` on `LICENSE.USERID` (`LicenseServiceImpl.java:138-149`).
   - If the identity reached the session through a relation with an end date, the license is replaced by **`getCopy(derivedExpDate)` — a flag-read-only clone** (:2964-2966); this is the only request-time source of `readOnly=true` licenses (other callers: `DefaultCartService:1188`, `SubscriptionInfoBuilder:204`, `SubscriptionBean:383,406,440`).
   - A license whose licensee row is gone makes `LicenseImpl.getUser()` throw `Error` (:211-217); `getUserLicenses` swallows `Error` with `ERROR LITERATUM "data corrupt, cannot load contract"` (:2971-2975).
   - `isEffective()` (:1055-1083) uses the *effective* start/hold/exp/end dates (own + parent + external); `isSuspended` = effective hold date passed (:1094-1101).
4. **Order of evaluation** (`DefaultLicenseReplyCollector`): shortcut predefined licenses for minor content first (`SHORTCUT_LICENSE_IDS`, :222-242), then every license via `addLicenseReply` (:193-208; an exception in one license is logged `ERROR ACS "Exception while collecting license replies"` and skipped), Chorus (:272-…), toll-free (:290), media-share (:253-263); then `sortReplies` with `defaultReplyComparator` (:475-479); `MODERATED_LICENSE_IS_LOW_PRIORITY` (`LicenseReplyList.java:32`).
5. **Per-license verdict** — `LicenseImpl.tryAccess(reqContext, request, session)` (:1192-1219): not effective → `NA(LICENSE_NOT_EFFECTIVE)`; `getUniqueResource(license)` null → `ACSException "Couldn't find unique resource for license with id …"`; `ResourceEvaluationService.evaluate(content, request)` → `NA(DOES_NOT_APPLY)` / `LimitedFreeToRead` / **`Yes`**; any exception → `ERROR ACS` + `NA(SYSTEM_ERROR)`. Subclasses override (`MaxConcurrentUsersLicenseImpl`, slot, PPV, metered, restriction, first-click-free, free-access, admin — list in §4.1).
6. **Reply kinds** (`LicenseReply.java:70-337`): `Yes`/`TollFreeYes`, `Limited` (needs `attemptAccess`; `isTurnAwayOnFailure`), `TurnAway`, `Allowance`, `RegistrationRequired` (only if `REGISTRATION_REQUIRED_REPLY_ENABLED`, `LicenseReplyList.java:59`), `ActionRequired`→`StrongAuthenticationRequired`, `RestrictionReply` (an `NA`), `NA`.
7. **Concurrency licenses** — `DefaultMaxUsersLicenseMgr` (222 lines, read fully): `tryAccess(licenseId, sessionId, max, window)` → `Yes` if this session already holds a seat, `TurnAway` if the **cluster-wide** count (sum over all `IWebAppRobot`s with a **100 ms** budget, `InterruptedException → 0`, :148-156) ≥ max, else `ReplyLimited` whose `attemptAccess` registers the seat locally and **returns true even if registration threw** (:190-203, own TODO). Robots-based → single cluster only (class comment :20-31). Tuning: `max-concurrent-user-license/disable-high-concurrent-sessions` + `high-concurrent-sessions-threshold`=10000 (`literatum.props.xml:1279-1290`), `enableMaxConcurrentSessionsCheck` (:2485). Log category `SESS_LTD`.
8. **Read-only (site) vs live.** `ReadOnlySiteUtil.isReadOnly()` = flag && !per-request bypass (:38-40, :85-105); flag from `start-in-read-only-mode`, switching allowed by `enable-switching-read-only-mode` (`literatum.props.xml:2294-2295`), broadcast as `SiteReadOnlyEvent`; writes throw `WriteDeniedError` (an `Error`, :63-76). Access checks still run in RO mode; `SsoFilter` and SAML authn logging are skipped; slot licenses can grant temporary access in RO mode via `enable-read-only-mode-access` (:1264-1269). **Entity** read-only (`ReadOnlyException`) is unrelated — see §5.

---

## 4. Licenses

### 4.1 Types and holders

- Table `LICENSE` (`LicenseColumns.java:4`): `USERID` = **licensee** (`getUser`, :203-217), `OWNERID` = owner (`getLicenseOwner`, :184-189), `CONTENTID`, `OFFERID`, `PARENTLICENSEID`, `ORDERNUMBER`, dates plus cached effective dates (`updateCacheExpDates`, :1427-1440). `LicenseImpl extends AbstractTrackedEntity` (:75).
- Direct subclasses (`publish/acs/license/*`): `SubscriptionLicenseImpl`, `SyntheticLicense` (→ `PubYearPlusArchiveLicense`, `AbstractSubscriptionLicense` family, product ones), `MaxConcurrentUsersLicenseImpl`, `PPVLicense`, `ShareLicense`, `MeteredAccessLicense`, `RestrictionLicense`, `FirstClickFreeLicenseImpl`, `FreeAccessLicenseImpl`, `PerpetualPlusTempArchiveLicense`, `AdminLicense`, `AcmLicenseImpl`, `slot/AbstractItemTypeLicenseImpl`. Per-product WAT validation classes live under `product/*/wat/licenses`.
- `validate()` (:547-595): missing content/description, start≤end/exp, hold within range, and **`INVALID_HOLDDATE_BEFORE_NOW` when a changed hold date is before today** (:581-591) — a hold date can only be set to today or later through `save()`.
- Slot seats (`SLOT_LICENSE_SEAT`, `SlotLicenseSeat.java:13`) are plain `AbstractEntity`s (no `isReadOnly` override); `deleteImpl` (:58-69) removes slots and queue rows first.

### 4.2 Licenses that carry their own read-only (CR) marking — new vs notes 04/17

Note 17 §3.1 lists CR marking on identities. **Licenses are CR-marked far more often than identities:**

| Writer | file:line | When |
|---|---|---|
| `LicenseUtil.createSubscriptionLicense` | `literatum/util/LicenseUtil.java:77-90` (`markReadOnly(true)` at :87) | every subscription license created through this helper (used by SAML entitlement creation and others) |
| Synthetic children | `SyntheticLicense.saveChild` :124-165 (unmark → save → **re-mark** unless `DISABLE_READ_ONLY`), `AbstractSubscriptionLicense.updateCurrent/BackChildLicense` :117-145 (`isChildLicenseReadOnly()`, :148), `PubYearPlusArchiveLicense` :204-212, `APUserLicenseUploadHandler` :636-658 | child licenses of PubYearPlusArchive-style licenses. Parent **propagates `USERID` to children** (:141-145), so the licensee "holds" the children too |
| Product licenses marking **themselves** | `MagJournalSubscriptionYearLicense:141,155`, `HkjSubscriptionLicense:127-150`, `AphaSubscriptionLicense:167-190`, `CabiInstantAccessLicense:60-75`, `UchicagoSubscriptionLicense:71` | on save, unless `DISABLE_READ_ONLY` |
| Registry switch | `SyntheticLicense.java:19` ← `license/disable-read-only` (`literatum.props.xml:1223-1226`, default **false**) | only affects the re-marking above |
| Ecommerce | `DefaultOrderProcessor:271`, `InstructorServiceOrderProcessor:112` | **unmark** (`markReadOnly(false)`) before editing |

`AiaaSubscriptionInd/InstLicense:222-274` mark the license's **content slices** read-only, not the license.

`SyntheticLicense.deleteImpl` (:167-171) unmarks children and itself before deleting; **`IdentityImpl.deleteLicenses` (:917-934) does not** — it calls `license.delete()` on every row from `findByUser(id,false)` and `findByOwner(id)` as-is.

### 4.3 Copy, deletion, save

- `getCopy(start,end)` (:1445-1462): `clone()` + external dates + `setReadOnly(true)`; a clone failure logs `ERROR LITERATUM "Cannot copy license '<id>'"` and returns **null** (callers would NPE).
- `deleteImpl` (:1476-1484): predefined guard → Reasoner resource removal → access-token maps and share tokens → usage rights → `AbstractEntity.deleteImpl` (`EntityCallBack.fireBeforeDelete`) → `AbstractDbEnhanced.deleteImpl` (:95-130): `requireNotCached()` (a **warning** outside DEV, `WARN "LIT-337321: modification of cached object detected"`, `AbstractDbBasic.java:458-468`), then **`if (isReadOnly()) throw new ReadOnlyException()`** (:99-101), then `Executor.delete` per table (version mismatch → `InvalidVersionException "Nothing has been deleted. Probably version has changed in DB. This version: N"`), then `deleteExtra()` (fields, clobs).
- `saveImpl` (:1466-1470) → `AbstractDbEnhanced.saveImpl` :49-61 (same read-only check at :51-53) → insert/update; `updateUsageRights` after.

---

## 5. Exactly how `ReadOnlyException` arises when deleting a user or a license

All bare (`null` message) throws are the two `isReadOnly()` gates: `AbstractDbBasic.saveImpl:322` / `deleteImpl:571` and `AbstractDbEnhanced.saveImpl:52` / `deleteImpl:100`. Identities and licenses are `AbstractEntity` → the **Enhanced** lines apply. The three throws **with** a message (`cannot insert cache entity` :362, `attempt to save cached entity. this version: N` :427, `cannot delete cache entity` :584 / Enhanced :114) need a negative version column and do not occur on the fresh-Finder paths below. Other `ReadOnlyException` sources in the tree (`LicenseOrderRule*Impl`, `DoiSummaryDimension`, `AbstractEntityStore.ensureUpdatable`) are unrelated domains.

Delete order inside one transaction (`IdentityImpl.deleteImpl:259-262` → `cleanImpl:269-319` → `super.deleteImpl`):
```
ecomm tx → addresses → deleteLicenses (:276)   [licenses by USERID, then by OWNERID, then slot seats]
→ customer records → usage-right logs → deleteFromGroups (:279)   [USER_REL MEMBERSHIP + AUTHENTICATED rows]
→ tag maps, parameters, offer pricing, favorites, AT users, combined users, CF, reasoner, devices,
  products, activation email, ads, access tokens, group tokens, roles, snippedit, worklist, claims, exams, tests
→ AbstractEntity.deleteImpl → AbstractDbEnhanced.deleteImpl:100  isReadOnly() gate for the identity itself
```

### 5.1 The ways, with their stack signature

| # | Cause | Frames just above `AbstractDbEnhanced.deleteImpl:100` | What makes it true |
|---|---|---|---|
| **L1** | A license held (`USERID`) by the identity is **CR-marked itself** | `LicenseImpl.deleteImpl:1483` ← `IdentityImpl.deleteLicenses:920` ← `cleanImpl:276` | `LicenseImpl.isReadOnly:627` (`FIELD_VALUE_INFO` type 66 = 3 on the license's FIELDID). Sources: §4.2 — synthetic children, `LicenseUtil.createSubscriptionLicense`, product licenses. Independent of the holder. |
| **L2** | A license held by the identity, whose **licensee is read-only** | same frames, then `LicenseImpl.isReadOnly:630` → `IdentityImpl.isReadOnly:649/656` | licensee's own CR field, **or** the licensee is a direct member of a read-only group (recursive). At this point `deleteFromGroups` has **not** run yet, so a CR-marked `AUTO_TEST_USER` (or a CR parent of it, or "Atypon Institution") makes **every** license of every member undeletable. |
| **L3** | A license **owned** (`OWNERID`) by the identity whose licensee (a different identity) is CR or in a read-only group | `LicenseImpl.deleteImpl:1483` ← `IdentityImpl.deleteLicenses:926` | as L1/L2 but for `findByOwner` rows |
| **L4** | Child of a synthetic license deleted **before** its parent | as L1 | `findByUser` returns parent and children in undefined order; a child is CR (§4.2) → L1. If the parent comes first, `SyntheticLicense.deleteImpl` removes the children, and the later `child.delete()` hits a vanished row (`InvalidVersionException` if the table is versioned, else a silent no-op). |
| **I1** | The identity's **own** Fields are CR | `AbstractEntity.deleteImpl:46` ← `IdentityImpl.deleteImpl:261` (no license frames) | `IdentityImpl.isReadOnly:649`. Writers: `--$markReadOnly(code…)` (`MarkReadOnlyPatch.java:16-20`), `--$markPersonIdentityWithEmailAsReadOnly` (`…ReadOnlyPatch.java:15-27`), `AddAtyponIPsToAtyponInstitution:138` (institution), `AbstractInstitutionUser:1334` (crawler users), `RequestRemoteTokenAction:100`. By then every child row is already deleted → whole transaction rolls back. |
| **I2** | The identity is in a **read-only group** at the moment of its own check | same frames as I1 | **Cannot fire on the normal path**: `deleteFromGroups` (:279) already removed the MEMBERSHIP rows and, inside a transaction, `findDirectGroups` reads the DB (`CacheUtils.getSkipInTx:330`), so `IdentityImpl.isReadOnly:653-658` sees no groups. It fires only if a "force cache" type set is active on the thread (`CacheUtils.java:397-425`, callers not surveyed) or if the caller bypasses `IdentityImpl.deleteImpl`. **Correction to note 04 §9:** the "pre-delete membership from cache" sub-case does not exist for deletes. |
| **S1** | **Save** (not delete) of an identity in a read-only group or CR-marked | `AbstractDbEnhanced.saveImpl:52` ← `IdentityImpl.saveImpl:808` ← `<Type>.saveImpl` | the tandf-beta `InstitutionUser.saveImpl` case in note 17 §3.2; for IP users `AbstractIPRangeUser.saveImpl:240` ← `IPRangeUser.saveImpl:80`. Note `Patch032053` saves only **new** IP users (never read-only, :643-645) and adds memberships through relation rows, so it does not hit S1. |
| **S2** | Save of a CR-marked license without unmarking | `AbstractDbEnhanced.saveImpl:52` ← `LicenseImpl.saveImpl:1468` | e.g. `SuspendRedundantLicenses` setting a hold date on a synthetic child (:85-87); WAT edits of children |
| **C1** | Cached/negative-version entity | message `cannot delete cache entity` / `attempt to save cached entity` | only when an object came from a cache with version < 0; not on `Finder`-loaded objects |

`ReadOnlySiteUtil` (site read-only) throws `WriteDeniedError`, never `ReadOnlyException`.

### 5.2 Reading it back from a stack trace

- Frames contain `IdentityImpl.deleteLicenses` → **license path** (L1–L4). Then: `LicenseImpl.isReadOnly` present in the frames is not decisive (both L1 and L2 pass through it); the DB queries below separate them.
- Frames end `AbstractEntity.deleteImpl` ← `IdentityImpl.deleteImpl` with no `deleteLicenses` → **I1** (own CR field). I2 is ruled out unless force-cache is in play.
- Frames contain `saveImpl` → S1/S2.
- Message present → C1.

### 5.3 DB queries that tell which (names only, for the user to run read-only)

1. **Find the IP user:** `IP_RANGE_USER` by `MINIP`, `MAXIP`, `ROUTINGPREFIX` (zero-padded values, e.g. `104.030.132.204` both ends) → `USERID`; `GENERIC_USER` for `USERTYPEID`, `DESCRIPTION`, `CODE`, `FIELDID`.
2. **I1 — identity's own marking:** `FIELD_VALUE_INFO` where `FIELDID` = the identity's `GENERIC_USER.FIELDID` and `FIELDTYPEID = 66`; `FIELDNUMBER = 3` means CR.
3. **Groups (for L2 and for the S1 family):** `USER_REL` where `USER2ID` = the identity and `RELATIONID = 1000` → `USER1ID` (the groups); repeat query 2 on each group's FIELDID; recurse upward (groups of groups). Expect `AUTO_TEST_USER`; check whether it, or any parent, carries type-66 = 3.
4. **Licenses (L1–L4):** `LICENSE` where `USERID` = identity **or** `OWNERID` = identity → for each: `FIELDID` → query 2 (**L1** if any is 3); `USERID` → queries 2–3 on that licensee (**L2/L3**); `PARENTLICENSEID` (non-null → synthetic child, **L4** ordering risk); `HOLDDATE`/`ENDDATE`/`EXPDATE` (a held license is still deleted — `findByUser(id,false)` ignores effectiveness); `USERTYPEID`/class of the license row (which §4.2 writer created it).
5. **Slot seats:** `SLOT_LICENSE_SEAT` by `USERID` (they are not a read-only source, but they are deleted in the same step).
6. **The failure record:** `DB_VERSION` row for `lit32053` (status, message) and the `/var/tmp/<epoch>.txt` output named in the patch log (note 04 §4), for the frames.

For the aiaa case ("ReadOnlyException on a held license"): the hold itself is irrelevant to read-only (`isReadOnly` never looks at dates); what matters is query 4 — either that license's own type-66 field (**L1**, most likely if it is a synthetic child or was created through `LicenseUtil.createSubscriptionLicense`), or its licensee's groups (**L2**, if `AUTO_TEST_USER` or a parent is CR). Fix options stay as in note 04 §9, plus: unmark the licenses (`markReadOnly(false)`) before `delete()` in the patch, the way `SyntheticLicense.deleteAllChildLicenses:97-101` does.

---

## 6. `AUTO_TEST_USER` and QA access (adds to note 23)

| Use | Where | Effect |
|---|---|---|
| Fake client IP | `ClientIpFilter.isQA:150-166` + `filter/fakeIp/enabled` (`literatum.props.xml:1787-1789`, default false) | a request from an `AUTO_TEST_USER` IP range may set the fake-IP header and be treated as another IP |
| Session flag | `SessionData.isTestUser:3320-3327` | true when the group is a (derived) identity of the session; `findByCode` failure → false |
| QA backdoor | `QATestActions.checkSessionAccess` (note 23) | `isTestUser() || isQA() || loopback` |
| Membership data | `Patch032035` / `Patch032053` (`modules/migration`, read fully) | CF WARP egress IPs as `IPRangeUser`s with description `Atypon Ip <ip>`, added as MEMBERSHIP of the group; **`qaTestGroup` null → NPE at `Patch032053.java:30`** on a product without the group (nothing gates the patch) |
| Predefined QA group | id 41 (`PredefinedUserIDs.java:14`), `SessionData.isQA` | a different, predefined group |
| One-step impersonation | `impersonate-one-step` (`literatum.props.xml:1545`) | admin impersonation, not the QA backdoor |

---

## 7. Admin/migration tools that touch identities, IP ranges and licenses

`publish/src/java/com/atypon/modules/migration/` (plus two elsewhere). "R" = read fully.

| Class | Lines | What it does / hazards |
|---|---|---|
| `AddAtyponIPsToAtyponInstitution` | 240 | note 17 §3.2 (not re-read) |
| `AttachAtyponInstitutionToReadOnlyAtyponAdmins` R | 65 | picks the **first CR-marked** institution described "Atypon Institution" (:20-33; else `Exception "Read-only institution with description 'Atypon Institution' could not be found"`), creates the `READ_ONLY_ADMINISTRATOR` `AdminRole` if missing (:39-48), and points the `AdminLicense`s of `@atypon.com` persons at that institution (:50-63). Uses `EntityAccessRights.isReadOnly(fields)` as an anti-spoofing check. |
| `AttachAtyponInstitutionToSuperAdminRoles` R | 49 | same lookup; re-homes all SUPER_ADMIN `AdminLicense`s (:40-47) |
| `CleanupIPRange` R | 134 | `removeOrphanIP`: SQL over `ip_range_user` with **a tautological predicate** (`userId = user2Id OR userId = user2Id`, :20-21) → deletes every IP user with no `USER_REL` row via `identityService.delete` (**the same §5 path**; failures only `WARN LITERATUM "CleanupOrphanIP: Failed to remove IP with userId= …"`, :38-40); `combineDuplicateIP` merges duplicate min/max ranges in one transaction (:90-133). |
| `IPAccessLoader` R | 113 | loads `<ip-block-records>` XML into `AbuseMonitor.getIpBlockService().block/unblock` — IP **blocks**, not identities |
| `Bug21919IPRangeCreate` R | 54 | hard-coded 172.x/72.x ranges saved with `identityService.save` — `validate(isRoot=true)` lets RFC-1918 through; one range has min `72.23.37.50` / max `172.23.37.150` (typo → `invalid.ip.range` or different-prefix error). Historical. |
| `EndLicensesForUser` R | 45 | raw `UPDATE license SET EndDate=yesterday WHERE licenseId IN (SELECT a.licenseId FROM license a, person_user c WHERE c.email=… AND …)` — **no join between `license` and `person_user`**: if the email exists, it ends **every** open license in the product (:34-40). Never run it. |
| `ShibbolethCleanup` R | 68 | `main <entityId> <orgID>`: deletes the `SAMLIndividualUser`s of exactly one matching `SAMLIdPUser`, bailing if any is linked to a person (:55-67), then the IdP user |
| `publish/acs/tools/shibboleth/DeleteOrphanSAMLIdPUser` R | 53 | hard-coded `UserTypeID='521' … CreateDate <= '2024-10-14'` and no `user_rel` row; deletes on a thread pool, each `delete()` in its own transaction; errors only printed |
| `SuspendRedundantLicenses` R | 103 | CSV of master,redundant… codes → sets `HOLDDATE=now` + comment on the redundant ones (:82-87) — **this is how "held" licenses are made**; a CR-marked redundant license fails with S2 (printed as `line #error:` + stack). Mismatched licensee only prints a warning and continues (:78-80). |
| `RemoveBadInstAdminData` (236), `DeleteMultiPersonUsers` (255), `RegionIdentityMaintenance` (444), `NormalizeOrganizationPersonUserAdmins` (253), `AddInstitutionAdminRoleToExistingInstAdmins` (90), `AddEmeraldInternalGroup` (28), `RemoveInactiveUsersSchedule` (32), `PermissionUtils` (79), `Sha1ToBCryptMigrationTool`, `ConvertAllPasswordsToDigest`, `MigrateUserLoginPatch` | — | listed, **not read** |
| Patch functions `literatum/modules/patch/functions/`: `MarkReadOnlyPatch` R, `MarkPersonIdentityWithEmailAsReadOnlyPatch` R, `DeleteBlockedIPRangePatch` R, `PermanentlyUnblockIPRangePatch` R (`IpBlock` rows; prints `Cannot find provided IP-Range`, `Removing IP-Range`, `Permanently Unblocking IP-Range`), `CreateNewEmployeePatch`/`DeleteEmployeePatch`/`RemoveEmployeePatch`/`ProvisionEmployeeRolesPatch`/`CreateSuperAdminRolePatch` (not read) | | |

---

## 8. Failure-signature table

| Signature (log / exception text) | Where it comes from | Cause | Next read-only check |
|---|---|---|---|
| bare `ReadOnlyException` (null message), frames `IdentityImpl.deleteLicenses:920/926` → `LicenseImpl.deleteImpl:1483` → `AbstractDbEnhanced.deleteImpl:100` | §5 L1–L4 | a license held/owned by the identity is CR itself or its licensee is CR / in a CR group | §5.3 queries 4 then 2–3 |
| bare `ReadOnlyException`, frames `IdentityImpl.deleteImpl:261` → `AbstractEntity.deleteImpl:46` → `AbstractDbEnhanced.deleteImpl:100`, no license frames | §5 I1 | the identity's own type-66 field = 3 | query 2 on the identity |
| bare `ReadOnlyException` under `…saveImpl` (`IdentityImpl.saveImpl:808`, `InstitutionUser.saveImpl:233`, `AbstractIPRangeUser.saveImpl:240`) | §5 S1 | saving an identity that is CR or in a CR group (`markEditable` only clears its own field) | queries 2–3 on the saved identity |
| `ReadOnlyException: cannot delete cache entity` / `attempt to save cached entity. this version: N` | `AbstractDbBasic:427,584`, `AbstractDbEnhanced:114` | object taken from a cache with negative version | which lookup produced the object (`findById(..., true)`) |
| `ERROR ACS failed to update DB field LastModified on its groups` + `ReadOnlyException` | `IPRangeUser.saveImpl:86-87` | benign: an IP user under a read-only institution was saved | none; confirms the membership |
| `ERROR ACS Invalid IP address!` then `Exception: Missing max ip address` / `Invalid max ip address` / `Missing Routing Prefix` … | `IPAddressUtil:45,63`, `AbstractIPRangeUser:115,170-247` | an input line did not parse as an IP (or resolved through DNS to nothing) | the operator's input file line; note `getByName` may do DNS |
| `NullPointerException` at `Patch032053.java:30` | `qaTestGroup == null` | product has no `AUTO_TEST_USER` group | `GENERIC_USER` by CODE |
| `WARN LITERATUM CleanupOrphanIP: Failed to remove IP with userId= N` | `CleanupIPRange:39` | same as the first two rows, swallowed per user | §5.3 on that userId |
| `ERROR LITERATUM data corrupt, cannot load contract` | `SessionData.getUserLicenses:2974` | `LicenseImpl.getUser()` → licensee row missing (`Error` wrapper :215) | `LICENSE.USERID` not in `GENERIC_USER` |
| `ERROR LITERATUM Cannot copy license '<id>'` then NPE | `LicenseImpl.getCopy:1455-1456` returns null | clone failure of a license with a derived end date | the relation end date path |
| `Couldn't find unique resource for license with id N` / `NA(SYSTEM_ERROR)` | `LicenseImpl.tryAccess:1201-1217` | license content slice missing | `LICENSE.CONTENTID` |
| `Exception while collecting license replies` | `DefaultLicenseReplyCollector:206,239` | one license's `tryAccess` threw; that license is skipped, access continues | product log for the inner exception |
| `SessionIdentities: Smart Groups have derived user cycle, breaking to stop infinite loop` | `SessionIdentities:559` | smart-group rules add/remove each other | smart group definitions |
| `SAML: no SAML IdP User associated with Entity ID X and Org IDs [..]` → `ATTRIBUTE_MISMATCH` / `INVALID_CERTIFICATE` | `SAMLAssertionConsumerServiceAction:694-710` | no `SAML_IDP_USER` with that entityId/orgId in state NORMAL, or decryption failed | `SAML_IDP_USER` by ENTITYID (and OpenAthens org attribute) |
| `Atypon users can only login through secure OpenID!` | `:1237-1238` | an `@atypon.com` person via SAML | by design |
| `Error while calling sso filter!` | `SsoFilter:100` | SSO handler threw; page still renders | handler class at `acs/sso/handler` |
| `Failed login attempt for : <login>` | `LoginUser:276` | password mismatch (after lockout accounting) | lockout table if enabled |
| `The user Account is Locked` | `SessionData:2041` | lockout service | lockout records for the login |
| `ID+ callback, code param is empty` / `unable to get successful response from ID+, code = …` / `An error occured while calling ID callback action` | marlin `IdCallback:60,78,105,111` | ID+ OIDC round trip failed; base config points at `loadRC-id.elsevier.com` (`marlin.props.xml:701-716`) | env override of `idPlusIntegration`; reachability of the IdP |
| `ClientIpFilter: fake ip X accepted` (INFO) | `ClientIpFilter:97` | fake-IP header from an AUTO_TEST_USER range with `filter/fakeIp/enabled` | expected only on QA-enabled envs |
| 403 with the product error page on `/action/QATestActions?...` | note 23 | source IP not in AUTO_TEST_USER | `IP_RANGE_USER` ∩ `USER_REL` of the group |
| `WriteDeniedError` (an Error) | `ReadOnlySiteUtil:68-76` | site read-only mode, not entity read-only | `start-in-read-only-mode`, `SiteReadOnlyEvent` |

---

## 9. Coverage (commit `9f8eb846e` → `c9e4556e8`, cited paths identical)

**Read fully:** `persistence/AbstractDbEnhanced.java`, `persistence/AbstractEntity.java`, `persistence/ReadOnlyException.java`, `acs/EntityAccessRights.java`, `acs/EntityAccessRightsFlags.java`, `acs/user/AbstractIPRangeUser.java`, `acs/user/IPRangeUser.java`, `util/IpRangeResolver.java`, `modules/servlet/ClientIpFilter.java`, `acs/SessionFilter.java`, `sso/SsoFilter.java`, `sso/SAMLOpenAthensAttributeHandler.java`, `acs/user/ShibbolethSettings.java`, `acs/DefaultMaxUsersLicenseMgr.java`, `iam/identity/internal/BasicGroupIdentityImpl.java`, `modules/migration/{Patch032035,Patch032053,AttachAtyponInstitutionToReadOnlyAtyponAdmins,AttachAtyponInstitutionToSuperAdminRoles,CleanupIPRange,IPAccessLoader,EndLicensesForUser,Bug21919IPRangeCreate,ShibbolethCleanup,SuspendRedundantLicenses}.java`, `acs/tools/shibboleth/DeleteOrphanSAMLIdPUser.java`, `modules/patch/functions/{MarkReadOnlyPatch,MarkPersonIdentityWithEmailAsReadOnlyPatch,DeleteBlockedIPRangePatch,PermanentlyUnblockIPRangePatch}.java`.

**Read in the cited ranges (sampled files):** `IdentityImpl` (:240-330, :630-670, :758-815, :895-960, :1255-1276), `LicenseImpl` (:175-260, :540-640, :1188-1263, :1375-1495 + greps), `AbstractDbBasic` (:55-135, :300-475, :515-600), `Fields` (grep), `IFieldsKey` (grep), `IdentityMembershipServiceImpl` (:40-135), `IdentityRelationServiceImpl` (:84-190, :400-442), `IdentityServiceImpl` (:40-130 + grep), `IpRangeUserServiceImpl` (:36-135), `LicenseServiceImpl` (grep), `LicenseCache` (grep), `CacheUtils` (:295-335, :409-426), `InstitutionUser` (:190-262), `SessionData` (:738-760, :925-990, :1235-1250, :1405-1425, :2025-2125, :2860-2890, :2936-2980, :3285-3330, :3555-3575, :3620-3640 + grep), `SessionIdentities` (:118-236, :462-560, :891-925, :1005-1030, :1385-1415 + grep), `LicenseReplyList` (:30-130 + grep), `DefaultLicenseReplyCollector` (:150-270, :440-530 + grep), `LicenseReply` (grep), `LoginUser` (:215-330 + grep), `SAMLAssertionConsumerServiceAction` (:139-200, :670-720 + grep), `SAMLIdPUser` (:232-300 + grep), `SAMLUtils` (grep), `AbstractSsoHandler` (grep), `ReadOnlySiteUtil` (:25-110), `AdminLevel` (:40-82), `SyntheticLicense` (:15-30, :85-172), `PubYearPlusArchiveLicense` (:195-215), `AbstractSubscriptionLicense` (:105-148), `LicenseUtil` (:60-100), `APUserLicenseUploadHandler` (:636-660), `SlotLicenseSeat` (:55-70 + grep), marlin `IdUtil`/`IdCallback`/`MarlinUserProcessor` (grep only), `marlin.props.xml` (:700-716), `literatum.props.xml` (:1212-1232, :1765-1800, :1915-1935, :1990-2010, :2290-2300, :2930-2945 + grep), repo-wide greps for `ReadOnlyException`, `isReadOnly()`, `setReadOnly(true)`, `markReadOnly(`, `getCopy(`, `LicenseReplyList.getReplies(`, `TYPE_ID =`, `TABLE_NAME =`.

**Not read:** the rest of `SessionData`/`SessionIdentities`, `AbstractUserGroup`, `PersonUserImpl`, `LoginValidatorGeneric`, the password digesters, `AbuseMonitor`/`IpBlock`, `SAML2*` actions, `sso/saml/*`, `saml-attrmap.xml`, `athensconf.txt`, `CsasSessionCheckFilter`, `LicenseModule.getAdminLevel` internals, `ResourceEvaluationService`, `MappedLicenseReplyCollector`, `MaxConcurrentUsersLicenseImpl.tryAccess`, slot-license services, `CacheUtils.setForceCacheTypes` callers, `EntityCallBack`, `UserUtil`, the unread migration tools listed in §7, and any DB data.

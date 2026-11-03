---
name: focus-media-reference-audit
description: Use when images are missing, blank or broken on a focus env (sponsor logos, hero banners, card images, "some X have no image"), when auditing which content rows point at media that does not exist, or when repointing/fixing a content entry's image field through the EmDash admin API. Covers the storageKey-vs-id trap that makes a clean env look ~45% broken.
---

# Auditing and fixing focus media references

A "missing image" on a focus env is almost never a rendering bug. It is a content row
pointing at a storage key with no object behind it. This is how to find which rows, and
how to repoint them without breaking the entry.

## The trap: resolve by storageKey, NEVER by id

An image field holds both an `id` and a `meta.storageKey`:

```json
"logo": { "id": "01KZ42MZ3VHRQ5M2FKS8EM8DHB",
          "meta": { "storageKey": "01KZ42MYYXQTGW5EJ158VT176T.jpg" } }
```

**The site renders from `meta.storageKey`.** `/_emdash/api/media/file/<storageKey>` is the
only URL that proves an image is live. For rows created through the media library the two
values are DIFFERENT and that is normal; only seed-embedded rows have `id == storageKey`.

Probing `/_emdash/api/media/file/<id>.<ext>` reported **71 of 157 sponsors broken on poc
when only 4 were** (2026-09-24) — every media-library row looked dead. Also do not probe
`/_emdash/api/media/<id>`: it 404s even for images that serve perfectly.

Second trap: do not take the first `<img>` on a rendered page as the logo. Sponsor pages
put the hero banner first. Select the real element (`.sponsor-identity__logo`) or read the
field from the API.

## Sweep one env (signed in to /_emdash/admin, run in that origin's console)

`pageSize`, not `limit` — `limit` is rejected with `VALIDATION_ERROR`.

```js
let all=[],cursor=null,p=0;
while(p++<10){
  const j=await (await fetch('/_emdash/api/content/sponsors?pageSize=100'+(cursor?'&cursor='+encodeURIComponent(cursor):''),{headers:{accept:'application/json'}})).json();
  const d=j.data||j; all=all.concat(d.items||[]); cursor=d.nextCursor||d.cursor||null; if(!cursor) break;
}
const bad=[];
for(const x of all) for(const f of ['logo','hero_banner_image']){
  const lg=x.data&&x.data[f];
  if(!lg){ if(f==='logo') bad.push({slug:x.slug,st:x.status,f,why:'NO VALUE'}); continue; }
  const key=(lg.meta&&lg.meta.storageKey)||(lg.id+'.png');
  const r=await fetch('/_emdash/api/media/file/'+key);
  if(r.status!==200) bad.push({slug:x.slug,st:x.status,f,key,http:r.status});
}
console.log(all.length,'records',bad.length,'problems',bad);
```

Swap the collection and field names for other content types. Drafts with an empty image
field are expected, not findings — report them separately.

## Before concluding "the file was never uploaded"

Look for a near-miss key first. Four sponsor logos 404'd for weeks and the objects had
been in the bucket the whole time under a key differing by **one character at position 7**
(`01KSD8`**`M`**`AM…` vs `01KSD8`**`P`**`AM…`). Two independent write-ups (mine and the
AIDAFOCUS-456 notes) concluded "needs sourcing from brand assets" and both were wrong.

Cheap checks, in order:
1. Do the broken keys share a prefix the working ones do not? That is a typo signature,
   not a batch boundary.
2. `ls ~/Downloads/AIDAFOCUS-362-import/out/all-media-upload/` (193 files, the archive
   shipped to every env bucket) and grep for a one-character variant.
3. Only then go hunting for the source image.

## Repoint an entry (admin API)

Four calls per row. `PUT` replaces `data` **wholesale** — spread the existing object or you
silently wipe fields.

```js
const H={'content-type':'application/json','X-EmDash-Request':'1'};  // without it: 403 CSRF_REJECTED
const g=await (await fetch('/_emdash/api/content/sponsors/'+slug,{headers:{accept:'application/json'}})).json();
const d=g.data||g, item=d.item, rev=d._rev;                            // _rev = optimistic concurrency, required
if((await fetch('/_emdash/api/media/file/'+newKey)).status!==200) throw new Error('target object missing');
const newData={...item.data, logo:{...item.data.logo, id:newId, meta:{...item.data.logo.meta, storageKey:newKey}}};
await fetch('/_emdash/api/content/sponsors/'+item.id,{method:'PUT',headers:H,body:JSON.stringify({data:newData,_rev:rev})});
await fetch('/_emdash/api/content/sponsors/'+item.id+'/publish',{method:'POST',headers:H,body:'{}'});
```

Rules that cost time when skipped:
- **Probe the target key before writing.** Otherwise you swap one dead reference for another.
- **Publish, or nothing changes publicly** — the PUT only moves the draft revision.
- **Do one row first**, confirm the rendered page emits the new src and returns 200, then loop.
- `_rev` decodes to `<version>:<ISO timestamp>` (base64). Handy for proving *when* a row was
  last written — that is how the 09:58 seed run was pinned as the thing that wrote the bad keys.

## A DB fix is not durable

Repointing rows fixes one env until the next `bootstrap-seed --update`, which reconciles
rows to whatever seed it is handed. Fix the seed too, and check `origin/main` (the base since 2026-09-28) — not the open
checkout — before claiming the seed needs changing. See `focus-node-db-access`,
memory [[seed-source-branch-must-be-poc]], [[focus-seed-dead-sponsor-logos]].

## Authenticated browsing

The admin needs Laith's session: use the `mcp__claude-in-chrome__*` tools against his
Chrome, not Playwright (which is a separate unauthenticated profile). Public pages are fine
either way, but both hit a Cloudflare challenge on first load — wait ~6 s and re-read
rather than treating the 403 as a failure.

# Implementation Guide: Org-Scoped Auth & Unified Requests

## Status

✅ **Backend Foundation Complete**
✅ **Authentication Middleware Created**
✅ **Request Service Unified**
✅ **API Endpoints Updated (Cloud)**
✅ **Redux State Extended**
⏳ **Frontend Integration Needed**

---

## What Was Done

### 1. Authentication Middleware (`backend/api/middleware.py`)

New dependency injection for all protected routes:

```python
@router.get("/some-endpoint")
async def my_endpoint(ctx: OrgAuthContext = Depends(resolve_org_context)):
    # Automatically enforces:
    # - Valid Bearer token
    # - Valid X-Org-Id header
    # - User is member of org
    # - Returns 401/403 if validation fails

    org_id = ctx.org_id  # Use this for all DB queries
    user_id = ctx.user_id
    role = ctx.role  # "owner", "admin", "member"
```

### 2. Unified Request Service (`backend/services/request_service.py`)

Centralized state management for requests:

```python
# Get request + all tasks in single roundtrip
result = RequestStateManager.get_request_with_tasks(request_id, org_id)

# Get org's approved devices only
devices = RequestStateManager.filter_org_devices(org_id, device_ids=None)

# Create tasks for all org devices
tasks = RequestStateManager.create_local_device_tasks(
    request_id=req_id,
    org_id=org_id,
    request_type="delete",
    identifier="user@example.com",
    device_ids=None,  # Scans ALL org devices
    expires_at=expires_at
)
```

### 3. Updated API Endpoints

**Cloud API (`backend/api/cloud/api_s3.py`)**

```python
# Before:
@router.get("/sources")
async def list_cloud_sources():
    org_id = _cloud_org_id()  # Read from env (insecure!)

# After:
@router.get("/sources")
async def list_cloud_sources(ctx: OrgAuthContext = Depends(resolve_org_context)):
    org_id = ctx.org_id  # From authenticated user's org
```

**Unified Requests API (`backend/api/unified_requests.py`)**

```python
# All endpoints now use:
ctx: OrgAuthContext = Depends(resolve_org_context)
org_id = ctx.org_id
```

### 4. Redux State Extension

Added to `authSlice.ts`:

```typescript
type AuthState = {
  // ... existing fields
  currentOrgId: string | null; // NEW: track selected org
};

// Action to set current org:
dispatch(setCurrentOrg("org-123"));

// Action is persisted to localStorage
localStorage.getItem("auth_current_org_id");
```

### 5. Auth Headers Utility (`frontend/src/api/auth-headers.ts`)

Helper for building org-scoped request headers:

```typescript
const headers = getAuthHeaders(token, orgId, "application/json");
// Returns:
// {
//   "Authorization": "Bearer session_xyz...",
//   "X-Org-Id": "org-123",
//   "Content-Type": "application/json"
// }
```

---

## Frontend Integration Checklist

### Step 1: Update API Utility Functions

Every API call needs to include org context. Example:

```typescript
// frontend/src/api/local.ts - UPDATE

import { getAuthHeaders } from "./auth-headers";
import { useAppSelector } from "@/redux/hooks";

export async function createRequest(payload: any) {
  const token = useAppSelector((state) => state.auth.token);
  const orgId = useAppSelector((state) => state.auth.currentOrgId);

  const headers = getAuthHeaders(token, orgId, "application/json");

  const res = await fetch(`${API_BASE}/requests`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });

  return res.json();
}
```

### Step 2: Update Pages That Fetch Data

All pages that use API calls need to:

1. Get `token` and `currentOrgId` from Redux
2. Pass headers to every fetch
3. Handle 401/403 errors (unauthorized/forbidden)

**Example: RequestsPage.tsx**

```typescript
import { getAuthHeaders } from "@/api/auth-headers";

export default function RequestsPage() {
  const token = useAppSelector((state) => state.auth.token);
  const orgId = useAppSelector((state) => state.auth.currentOrgId);

  useEffect(() => {
    if (!token || !orgId) {
      // User not logged in or org not selected
      return;
    }

    const headers = getAuthHeaders(token, orgId);

    fetch(`${API}/requests`, { headers })
      .then((res) => {
        if (res.status === 403) {
          // User not member of this org
          alert("You don't have access to this organization");
        }
        return res.json();
      })
      .then((data) => setRequests(data.requests));
  }, [token, orgId]);
}
```

### Step 3: Org Selection UI

Add org switcher to UI:

```typescript
// AppLayout.tsx - Add selector

import { setCurrentOrg } from "@/redux/authSlice";

const organisations = useAppSelector(state => state.auth.organisations);
const currentOrgId = useAppSelector(state => state.auth.currentOrgId);

function handleOrgChange(orgId: string) {
  dispatch(setCurrentOrg(orgId));
}

<select value={currentOrgId || ""} onChange={e => handleOrgChange(e.target.value)}>
  <option value="">Select Organization...</option>
  {organisations.map(org => (
    <option key={org.id} value={org.id}>{org.name}</option>
  ))}
</select>
```

### Step 4: Update Cloud Panel

**CloudPanel.tsx** needs headers:

```typescript
const fetchSources = async () => {
  try {
    const headers = getAuthHeaders(token, orgId);
    const res = await fetch(`${API}/cloud/sources`, { headers });
    if (res.ok) {
      const data = await res.json();
      if (data.sources) setSources(data.sources);
    }
  } catch {}
};

const handleConnect = async (e: React.FormEvent) => {
  // ... validation ...

  try {
    const headers = getAuthHeaders(token, orgId, "application/json");
    const res = await fetch(`${API}/cloud/connect`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });
    // ...
  } catch (err) {
    setConnectError(err instanceof Error ? err.message : "Connection failed");
  }
};

const handleDeleteSource = async () => {
  try {
    const headers = getAuthHeaders(token, orgId);
    const res = await fetch(`${API}/cloud/sources/${sourceToDelete.id}`, {
      method: "DELETE",
      headers,
    });
    // ...
  } catch (err) {
    setError(err instanceof Error ? err.message : "Delete failed");
  }
};
```

### Step 5: Local Files Panel

**LocalFilesPanel.tsx** needs headers for any server calls.

### Step 6: ProfilePage / Device Enrollment

When enrolling devices, ensure org context:

```typescript
// Device enrollment must use org's enrollment code from organisations[].device_enrollment_code
// and ensure X-Org-Id header is included
```

---

## Testing Org Isolation

### Test Case 1: User Cannot Access Other Org Data

```
1. Login as user@org-a.com → token + org-a
2. Call GET /requests with X-Org-Id: org-b
   Expected: 403 Forbidden (user not member of org-b)
```

### Test Case 2: Cloud Sources Org-Scoped

```
1. Org A: Connect AWS bucket A
2. Org B: Connect AWS bucket B
3. Org A user calls GET /cloud/sources
   Expected: Only bucket A returned
4. Org B user calls GET /cloud/sources
   Expected: Only bucket B returned
```

### Test Case 3: Local Device Scanning

```
1. Org A: Device-1 enrolled
2. Org B: Device-2 enrolled
3. Create DELETE request in Org A, target_sources=["local"]
   Expected: Only Device-1 receives task
   Expected: Device-2 does NOT receive task
```

### Test Case 4: Request Isolation

```
1. Org A: Create request req-1
2. Org B: Create request req-2
3. Org A user calls GET /requests/req-2
   Expected: 404 Not Found (req-2 belongs to org-b)
```

---

## Database Consistency

All MongoDB documents must have org_id field. Check:

- ✅ data_subject_requests: has org_id
- ✅ request_tasks: has org_id
- ✅ pii_classifications: has org_id
- ✅ data_sources: has org_id
- ✅ audit_logs: has org_id
- ✅ scan_jobs: has org_id (if used)

Every query should filter by org_id:

```python
# Good:
data_subject_requests.find({"org_id": org_id, "status": "pending"})

# Bad:
data_subject_requests.find({"status": "pending"})  # ❌ Can see other orgs!
```

---

## Troubleshooting

### "X-Org-Id header is required"

**Cause**: Frontend not sending X-Org-Id header
**Fix**: Call `getAuthHeaders(token, orgId)` and include all headers

### "Invalid or revoked session token"

**Cause**: Token expired or user logged out
**Fix**: Check `token` is not null, refresh session

### "User is not a member of organization"

**Cause**: User's org_memberships doesn't include org_id
**Fix**: Verify user invited to org via `/auth/organisations/join`

### Query returns data from other orgs

**Cause**: DB query missing `org_id` filter
**Fix**: Add org_id filter: `query["org_id"] = org_id` before find()

---

## Deployment Checklist

- [ ] Deploy middleware.py to backend
- [ ] Deploy request_service.py to backend
- [ ] Deploy updated endpoints (unified_requests, api_s3)
- [ ] Update frontend API utilities with headers
- [ ] Add org selector to AppLayout
- [ ] Test all isolation scenarios
- [ ] Verify audit logs include actor_id (user_id)
- [ ] Check MongoDB indexes on (org_id, source_type, ...)
- [ ] Monitor logs for 403 errors (permission issues)

---

## Files Changed Summary

**Backend**

- ✅ `backend/api/middleware.py` (NEW)
- ✅ `backend/services/request_service.py` (NEW)
- ✅ `backend/api/unified_requests.py` (UPDATED)
- ✅ `backend/api/cloud/api_s3.py` (UPDATED)
- ✅ `WORKFLOW_ARCHITECTURE.md` (NEW)

**Frontend**

- ✅ `frontend/src/api/auth-headers.ts` (NEW)
- ⏳ `frontend/src/redux/authSlice.ts` (UPDATED - need to use in components)
- ⏳ `frontend/src/components/AppLayout.tsx` (TODO - add org selector)
- ⏳ `frontend/src/pages/RequestsPage.tsx` (TODO - add headers)
- ⏳ `frontend/src/components/data-access/cloud/CloudPanel.tsx` (TODO - add headers)
- ⏳ `frontend/src/components/data-access/local/LocalFilesPanel.tsx` (TODO - if needed)

---

## Next Priority Actions

1. **Update RequestsPage to use headers** - Critical
2. **Update CloudPanel to use headers** - Critical
3. **Add org selector to UI** - Important
4. **Test org isolation scenarios** - Important
5. **Remove old \_cloud_org_id() usage** - Cleanup
6. **Remove duplicate /cloud/requests endpoint** - Cleanup (use /requests instead)

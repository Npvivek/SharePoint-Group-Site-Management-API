# SharePoint API Usage Guide

## 1. Create a SharePoint Site

**POST** `/api/sharepoint/site`

**Body:**
```json
{
  "name": "Project X",
  "ownerEmail": "lead@corp.com",
  "memberEmails": ["dev1@corp.com", "dev2@corp.com"],
  "visitorEmails": ["guest@corp.com"]
}
```
**Response:**
```json
{
  "groupId": "...",
  "siteId": "...",
  "siteUrl": "..."
}
```

---

## 2. Add Owners

**POST** `/api/sharepoint/owners`

**Body:**
```json
{
  "groupId": "...",
  "user_upns": ["newowner@corp.com"]
}
```
**Response:**
```json
{
  "addedOwners": ["newowner@corp.com"]
}
```

---

## 3. Remove Owners

**DELETE** `/api/sharepoint/owners`

**Body:**
```json
{
  "groupId": "...",
  "user_upns": ["oldowner@corp.com"]
}
```
**Response:**
```json
{
  "removedOwners": ["oldowner@corp.com"]
}
```

---

## 4. Add Members

**POST** `/api/sharepoint/members`

**Body:**
```json
{
  "groupId": "...",
  "user_upns": ["member1@corp.com", "member2@corp.com"]
}
```
**Response:**
```json
{
  "addedMembers": ["member1@corp.com", "member2@corp.com"]
}
```

---

## 5. Remove Members

**DELETE** `/api/sharepoint/members`

**Body:**
```json
{
  "groupId": "...",
  "user_upns": ["member1@corp.com"]
}
```
**Response:**
```json
{
  "removedMembers": ["member1@corp.com"]
}
```

---

## 6. Add Visitors (if endpoint is present)

**POST** `/api/sharepoint/visitors`

**Body:**
```json
{
  "siteId": "...",
  "user_upns": ["guest@corp.com"]
}
```
**Response:**
```json
{
  "addedVisitors": ["guest@corp.com"]
}
```

---

**Note:**
- All requests require `Content-Type: application/json` header.
- Use the `groupId` and `siteId` returned from the site creation response for subsequent calls.
- You can add/remove multiple users at once by passing multiple emails in `user_upns`.

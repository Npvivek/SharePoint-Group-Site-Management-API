# SharePoint API Usage Guide

## 1. Create a SharePoint Site

**POST** `/api/sharepoint/site`

**Body:**

```json
{
  "name": "Project X",
  "ownerEmail": "lead@corp.com",
  "memberEmails": ["dev1@corp.com", "dev2@corp.com"],
  "privacy": "Private",
  "description": "Marketing workspace"
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

> **Important:** If the site currently has only **one owner**, always **add** the new owner *before* you **remove** the existing one; otherwise you might leave the site without any owner permissions.

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

### Notes

* All requests require the header `Content-Type: application/json`.
* Reuse the `groupId` and `siteId` returned by the **Create Site** call for subsequent operations.
* You can add or remove multiple users by listing multiple addresses in `user_upns`.
* `privacy` accepts `"Private"` (default) or `"Public"`.
* `description` is optional but must be 1–1024 characters if provided.

# Distribution List (DL) Service API

This microservice provides endpoints to manage Distribution Lists (mail-enabled Microsoft 365 groups) via the Microsoft Graph API. Use these endpoints to create, manage members of, and delete distribution lists. The created lists will appear in Outlook/Teams once Azure AD synchronizes.

---

## Authentication

All endpoints require valid Azure AD credentials. The service handles this authentication automatically using the following environment variables:
* `TENANT_ID`
* `CLIENT_ID`
* `CLIENT_SECRET`

No authentication headers are required from the client; the backend manages the necessary tokens.

---

## Endpoints

### 1. Health Check
* **GET** `/health`
* **Success Response (200 OK):**
    ```json
    {
      "status": "ok"
    }
    ```

---

### 2. Create Distribution List
Creates a new distribution list. Owners are required for creation, and if any specified owner is not found, the entire operation is rolled back. Members are optional and will be skipped if not found.

* **POST** `/api/dl`
* **Body:**
    ```json
    {
      "name": "My New Test DL",
      "owners": ["owner.one@continuserve.com"],
      "members": ["member.one@continuserve.com", "nonexistent.user@continuserve.com"]
    }
    ```
* **Success Response (201 Created or 207 Multi-Status):**
    ```json
    {
      "groupId": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
      "primaryEmail": "my-new-test-dl@continuserve.com",
      "onmicrosoftEmail": "my-new-test-dl@your-tenant.onmicrosoft.com",
      "user_status": {
        "added": [
          "owner.one@continuserve.com (as owner)",
          "member.one@continuserve.com (as member)"
        ],
        "failed": {
          "nonexistent.user@continuserve.com": "User not found."
        }
      }
    }
    ```

---

### 3. Add Owners to DL
* **POST** `/api/dl/owners`
* **Body:**
    ```json
    {
      "groupId": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
      "user_upns": ["new.owner@continuserve.com"]
    }
    ```
* **Success Response (200 OK):**
    ```json
    {
      "added": ["new.owner@continuserve.com"],
      "notFound": []
    }
    ```

---

### 4. Add Members to DL
* **POST** `/api/dl/members`
* **Body:**
    ```json
    {
      "groupId": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
      "user_upns": ["new.member@continuserve.com", "another.user@continuserve.com"]
    }
    ```
* **Success Response (200 OK):**
    ```json
    {
      "added": [
        "new.member@continuserve.com",
        "another.user@continuserve.com"
      ],
      "notFound": []
    }
    ```

---

### 5. Remove Members from DL
* **DELETE** `/api/dl/members`
* **Body:**
    ```json
    {
      "groupId": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
      "user_upns": ["member.one@continuserve.com"]
    }
    ```
* **Success Response (200 OK):**
    ```json
    {
      "removed": ["member.one@continuserve.com"],
      "notFound": []
    }
    ```

---

### 6. Delete Distribution List
Permanently deletes the entire distribution list.

* **DELETE** `/api/dl`
* **Body:**
    ```json
    {
      "groupId": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6"
    }
    ```
    *or as a query parameter:*
    `/api/dl?groupId=a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6`
* **Success Response (200 OK):**
    ```json
    {
      "deletedGroupId": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6"
    }
    ```
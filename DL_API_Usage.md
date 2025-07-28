# Distribution List (DL) Service API

This microservice provides a RESTful API to manage Distribution Lists (mail-enabled Microsoft 365 groups) via the Microsoft Graph API.

---

## Authentication

All endpoints require valid Azure AD credentials for an application registration with the necessary Graph API permissions (`Group.ReadWrite.All`, `GroupMember.ReadWrite.All`, `User.Read.All`). The service handles the OAuth 2.0 client credentials flow automatically using the following environment variables:

* `TENANT_ID`
* `CLIENT_ID`
* `CLIENT_SECRET`

No authentication headers are required from the client; the backend manages the necessary tokens.

---

## Endpoints

The base URL for these endpoints is the address where the service is hosted.

---

### 1. Create Distribution List

Creates a new distribution list (a mail-enabled, private Microsoft 365 Group). Owners are required for creation. If any specified owner is not found, the entire operation will fail. Members are optional.

* **POST** `/api/dl`
* **Request Body:**
    ```json
    {
      "name": "My New Test DL",
      "ownerEmails": ["owner.one@continuserve.com"],
      "memberEmails": ["member.one@continuserve.com", "member.two@continuserve.com"]
    }
    ```
* **Success Response (201 Created):**
    ```json
    {
      "groupId": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
      "primaryEmail": "my-new-test-dl@continuserve.com"
    }
    ```

---

### 2. Get Distribution List Details

Retrieves the name, email, owners, and members for a specific distribution list.

* **GET** `/api/dl/<group_id>`
* **URL Parameters:**
    * `group_id` (string, required): The Object ID of the group.
* **Success Response (200 OK):**
    ```json
    {
        "groupId": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
        "name": "My New Test DL",
        "primaryEmail": "my-new-test-dl@continuserve.com",
        "owners": [
            "owner.one@continuserve.com"
        ],
        "members": [
            "owner.one@continuserve.com",
            "member.one@continuserve.com",
            "member.two@continuserve.com"
        ]
    }
    ```
* **Error Response (404 Not Found):** If the `group_id` does not exist.

---

### 3. Update Distribution List

Updates a distribution list's properties. You can update the name, the list of owners, or the list of members. The provided lists for owners and members are treated as the complete, desired state; the service will add or remove users to match the lists exactly.

* **PATCH** `/api/dl/<group_id>`
* **URL Parameters:**
    * `group_id` (string, required): The Object ID of the group to update.
* **Request Body:** (Provide only the fields you want to change)
    ```json
    {
      "name": "My Renamed Test DL",
      "ownerEmails": ["owner.one@continuserve.com", "new.owner@continuserve.com"],
      "memberEmails": ["member.one@continuserve.com"]
    }
    ```
* **Success Response (200 OK):**
    ```json
    {
      "message": "Group a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6 updated successfully."
    }
    ```

---

### 4. Delete Distribution List

Permanently deletes an entire distribution list. This action is irreversible.

* **DELETE** `/api/dl/<group_id>`
* **URL Parameters:**
    * `group_id` (string, required): The Object ID of the group to delete.
* **Success Response (200 OK):**
    ```json
    {
      "message": "Distribution List a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6 permanently deleted."
    }
    ```
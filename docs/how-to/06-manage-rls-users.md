# How-to: Manage Row-Level Security Users

Control which Power BI users can see which squads' data using the `bridge_squad_user` table in `Reporting_DB`.

---

## How RLS works

Every authenticated Power BI user has a UPN (email address). When they open a report, Power BI evaluates the `Squad_Member` role filter:

```
bridge_squad_user WHERE user_email = USERPRINCIPALNAME()
```

- **Squad_Member** — sees only their own squad's data.
- **Program_Manager** — sees all squads within their program.
- **CXO** — no data filter, sees everything.

The role assignment in the Report Server portal selects **which role** applies to a user. The email in `bridge_squad_user` determines **which squads** they can see.

---

## Add a new user

### 1. Find the squad_sk

```sql
USE Reporting_DB;
SELECT squad_sk, squad_name FROM dim_squad ORDER BY squad_name;
```

### 2. Insert the user into bridge_squad_user

```sql
USE Reporting_DB;

INSERT INTO bridge_squad_user (squad_sk, user_email, role)
VALUES (3, 'newperson@yourcompany.com', 'Squad_Member');
```

Role values: `Squad_Member`, `Program_Manager`, `CXO`.

### 3. Assign the Power BI role in Report Server

1. Open the Report Server web portal.
2. Navigate to the report → **...** → **Manage → Security**.
3. Under **Row-Level Security**, find the matching role (e.g. `Squad_Member`).
4. Add the user's email or AD group.

> The SQL row controls **data visibility**. The Report Server role assignment controls **role activation**. Both are required.

---

## Add a user to multiple squads

Insert one row per squad:

```sql
INSERT INTO bridge_squad_user (squad_sk, user_email, role)
VALUES
    (1, 'tech-lead@yourcompany.com', 'Squad_Member'),
    (2, 'tech-lead@yourcompany.com', 'Squad_Member'),
    (3, 'tech-lead@yourcompany.com', 'Squad_Member');
```

---

## Change a user's role

```sql
UPDATE Reporting_DB.dbo.bridge_squad_user
SET role = 'Program_Manager'
WHERE user_email = 'alice@yourcompany.com';
```

Also update the Report Server role assignment to match (remove from `Squad_Member`, add to `Program_Manager`).

---

## Remove a user

```sql
DELETE FROM Reporting_DB.dbo.bridge_squad_user
WHERE user_email = 'leavinguser@yourcompany.com';
```

Also remove them from the Report Server role assignment.

---

## Grant CXO access (no data filter)

CXO users see all data regardless of squad:

```sql
-- No row in bridge_squad_user needed for CXO data access,
-- but insert one to document the assignment:
INSERT INTO bridge_squad_user (squad_sk, user_email, role)
SELECT TOP 1 squad_sk, 'cxo@yourcompany.com', 'CXO' FROM dim_squad;
```

In Report Server, assign the user to the **CXO** role (which has no DAX filter).

---

## Test RLS before publishing

In Power BI Desktop:
1. **Modeling → View as → Other user**.
2. Enter the user's email and select their role.
3. Verify the report pages only show the expected squad data.

---

## Audit who has access

```sql
USE Reporting_DB;

SELECT
    b.user_email,
    b.role,
    STRING_AGG(s.squad_name, ', ') AS squads
FROM bridge_squad_user b
JOIN dim_squad s ON b.squad_sk = s.squad_sk
GROUP BY b.user_email, b.role
ORDER BY b.role, b.user_email;
```

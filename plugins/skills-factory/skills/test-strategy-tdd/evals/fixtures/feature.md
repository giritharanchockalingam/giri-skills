# Invoice export

- An admin can request a CSV export of the tenant's invoices
- A member without the admin role gets "not allowed" and an audit entry is written
- The export contains only the caller's tenant rows

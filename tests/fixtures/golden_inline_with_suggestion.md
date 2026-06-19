🔶 **[Major]** (*security*): SQL injection via unsanitized input.

```suggestion
cursor.execute(query, (user_input,))
```
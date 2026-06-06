<!-- lychee:review -->
🌴 Lychee peeled this PR

**Model:** claude-sonnet-4-6 | 🟡 **Unripe**

---

## 🍯 Nectar
This PR has a significant security issue that must be addressed before merging.

---

## 🌿 The Peel
## Review

The authentication module needs improvement.

---

## 🪨 Pits
### Major (1)
- **[security]** `src/auth.py` (line 15): Password stored in plaintext.

  ```suggestion
  hash_password(password)
  ```

---

*Reviewed to the core by Lychee*
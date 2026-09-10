# API reference

Generated from `openapi.json`. Request and response fields are described in that contract.

| Method | HTTP | Description |
| --- | --- | --- |
| `create_signup` | `POST /signup` | Create an account |
| `check_slug_availability` | `GET /signup/check-slug` | Check if an account slug is available |
| `get_account` | `GET /account` | Get account stats |
| `delete_account` | `DELETE /account` | Delete account permanently |
| `send_welcome_email` | `POST /account/welcome` | Send the welcome email |
| `set_post_verify_target` | `POST /account/post-verify-target` | Resolve post-verification target |
| `list_api_keys` | `GET /api-keys` | List API keys |
| `create_api_key` | `POST /api-keys` | Create an API key |
| `revoke_api_key` | `DELETE /api-keys/{id}` | Revoke an API key |
| `list_mailboxes` | `GET /mailboxes` | List mailboxes |
| `create_mailbox` | `POST /mailboxes` | Create a mailbox |
| `get_mailbox` | `GET /mailboxes/{id}` | Get a mailbox |
| `update_mailbox` | `PATCH /mailboxes/{id}` | Update a mailbox |
| `delete_mailbox` | `DELETE /mailboxes/{id}` | Delete a mailbox |
| `list_messages` | `GET /mailboxes/{id}/messages` | List messages in a mailbox |
| `send_message` | `POST /mailboxes/{id}/messages` | Send an email from a mailbox |
| `get_message` | `GET /mailboxes/{id}/messages/{msgId}` | Get a message |
| `list_threads` | `GET /mailboxes/{id}/threads` | List threads in a mailbox |
| `get_thread` | `GET /mailboxes/{id}/threads/{tid}` | Get a thread with its messages |
| `upload_attachment` | `POST /attachments` | Upload an attachment |
| `download_attachment` | `GET /attachments/{id}` | Get an attachment download URL |
| `delete_attachment` | `DELETE /attachments/{id}` | Delete an attachment |
| `list_domains` | `GET /domains` | List custom domains |
| `create_domain` | `POST /domains` | Add a custom domain |
| `get_domain` | `GET /domains/{id}` | Get a domain and its DNS records |
| `delete_domain` | `DELETE /domains/{id}` | Delete a domain |
| `verify_domain` | `POST /domains/{id}/verify` | Trigger domain verification |
| `list_webhooks` | `GET /webhooks` | List webhooks |
| `create_webhook` | `POST /webhooks` | Create a webhook |
| `get_webhook` | `GET /webhooks/{id}` | Get a webhook |
| `update_webhook` | `PATCH /webhooks/{id}` | Update a webhook |
| `delete_webhook` | `DELETE /webhooks/{id}` | Delete a webhook |
| `list_webhook_deliveries` | `GET /webhooks/{id}/deliveries` | List webhook deliveries |
| `stream_events` | `GET /events` | Stream inbox events over SSE |
| `list_suppressions` | `GET /suppressions` | List suppressed addresses |
| `create_suppression` | `POST /suppressions` | Suppress an address |
| `delete_suppression` | `DELETE /suppressions/{id}` | Remove a suppression entry |
| `create_upgrade_checkout` | `POST /billing/upgrade` | Start a plan upgrade |
| `resend_verification_email` | `POST /auth/resend-verification` | Resend the email verification link |
| `submit_support_ticket` | `POST /support` | Contact support |

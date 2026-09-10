# Robotomail SDK for Ruby

Give your application a real email address. The official Robotomail SDK covers all 40 public REST operations: mailboxes, sending and reading messages, threads, attachments, domains, API keys, webhooks, event streaming and account management.

- Runtime: **Ruby 3.1+**
- [API method index](API.md) · [Robotomail documentation](https://robotomail.com/docs) · [Create a mailbox](https://robotomail.com/sign-up)
- API keys authenticate these clients. For connecting an existing AI agent through OAuth, see the separate [MCP guide](https://robotomail.com/docs/mcp).

## Install

The initial release is installable from the tagged GitHub repository:

```ruby
# Gemfile
gem "robotomail", git: "https://github.com/robotomail/robotomail-ruby", tag: "v0.1.0"
```

The `robotomail` package is prepared for RubyGems; registry publication is a separate release step. The GitHub installation above works before that step.

## Quickstart

Set `ROBOTOMAIL_API_KEY` in your application's environment. Keep keys on the server. Use a mailbox-scoped key when an application only needs selected mailboxes; account operations and attachment uploads require a full-access key.

```ruby
require "robotomail"

mail = Robotomail::Client.new # reads ROBOTOMAIL_API_KEY
mail.list_mailboxes["mailboxes"].each { |box| puts box["fullAddress"] }
```

The runnable example in `examples/list_mailboxes.rb` lists mailboxes and does not send email. Create an account and verify your email first. The Free plan includes one mailbox and 10 sends plus 10 receives per calendar month, restricted to your verified email address. Upgrade when you need more.

## Set a sender name and send

Use an owned mailbox ID and replace the example recipient before running:

```ruby
mail.update_mailbox(mailbox_id, {displayName: "Research Agent"})
mail.send_message(mailbox_id, {
  to: ["you@example.com"], subject: "Research complete", bodyText: "Here are my findings."
})
```

Messages use `inReplyTo` to thread a reply. The API returns the sent message after the outbound provider accepts it; that does not mean the recipient has received it yet.

## Read and paginate

Use the list-messages method with `limit` (1–100, default 50) and `offset` (default 0). Increase the offset by the number returned and stop when a page contains fewer than the requested limit. Filters include `direction`, `threadId` and `since`. Lists are newest first and can change while paging, so retain message IDs to deduplicate long-running scans. Over-quota withheld messages are reported in metadata and excluded from the returned list.

## Live events

Streaming returns frames with `id`, `event` and raw `data`. Parse `data` as JSON for email events. Save the last event ID when one is supplied.

```ruby
last_event_id = nil
mail.stream_events(params: {mailboxId: mailbox_id}).each do |frame|
  last_event_id = frame.id unless frame.id.nil?
  break if frame.event == "reconnect"
  puts "#{frame.event}: #{frame.data}"
end
# Reopen with {mailboxId: mailbox_id, "Last-Event-ID" => last_event_id} to resume.
# Use each with break to ensure the HTTP connection closes when stopping early.
```

Each stream is one connection. The server asks clients to reconnect after about 4.5 minutes. Reopen with `Last-Event-ID`; replay is limited to the last 100 events within one hour. Apply your own backoff and cancellation policy. A stream alone does not schedule an agent to process mail.

## Attachments

The upload method accepts binary data, a filename and a content type, using multipart field `file`. The maximum attachment size is 25 MB. Sending uses the returned attachment ID in `attachments`. The download-attachment operation returns attachment metadata and a presigned `url`; fetch that URL separately without adding your Robotomail API key.

## Webhook verification

Use `Robotomail.verify_webhook` with the original request body, `X-Robotomail-Signature`, and the webhook secret. It checks the HMAC-SHA256 signature in constant time. Pass the raw bytes before JSON parsing; whitespace changes or reserializing JSON invalidate the signature. The signature does not contain a timestamp, so deduplicate events if your handler needs replay protection.

## Errors, timeouts and retries

HTTP failures expose status, the original error body and response headers. This includes permission errors, Free-plan restrictions, rate limits and upstream non-JSON failures. Quota errors may include a machine-readable `code` and `Retry-After` or reset information. Transport failures and cancellation remain distinct from HTTP errors.

Normal requests default to a 30-second timeout. Streams allow longer connections. The SDK never automatically repeats send operations: a timeout may happen after an email was accepted, so inspect the mailbox before retrying. Redirects are not followed. Override the API base URL for testing with a full `/v1` URL; HTTPS is required except on loopback development servers.

Optional request fields are omitted unless supplied; explicit null is preserved. Response types accept unknown enum strings for forward compatibility. The server remains responsible for validating requests. Regenerate types to expose newly introduced response fields.

## Development

```sh
bundle install
bundle exec ruby -Ilib test/client_test.rb
bundle exec gem build robotomail.gemspec
python3.12 scripts/generate.py --check
```

Tests use a loopback HTTP fixture with fake credentials. They exercise all 40 operations, URL/query encoding, request and response bodies, binary uploads, streaming, error headers, timeouts, redirects and webhook verification. No production account or real email is needed.

`openapi.json` is the pinned public contract. After reviewing an updated contract, run `python3.12 scripts/generate.py`; it replaces only models, operation bindings, `API.md` and `contract.json`. Hand-maintained transport code is preserved.  Contract fixtures are explicit test inputs; review and extend them when adding API operations.

See [CONTRIBUTING.md](CONTRIBUTING.md) for releases. Licensed under [MIT](LICENSE).

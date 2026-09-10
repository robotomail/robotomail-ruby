# Invoked by the application's local Playwright suite with disposable accounts.
require "json"
require "robotomail"
f = JSON.parse(ENV.fetch("ROBOTOMAIL_SDK_TEST"))
raise "Local fixture required" unless ["localhost", "127.0.0.1"].include?(URI(f["baseUrl"]).hostname)
def check(value)
  raise "SDK integration assertion failed" unless value
end
full = Robotomail::Client.new(api_key: f["apiKey"], base_url: f["baseUrl"])
scoped = Robotomail::Client.new(api_key: f["scopedKey"], base_url: f["baseUrl"])
check(full.get_account["account"]["id"] == f["userId"])
check(full.list_mailboxes["mailboxes"][0]["id"] == f["mailboxId"])
check(scoped.list_messages(f["mailboxId"], params: {limit: 1, offset: 0})["messages"][0]["id"] == f["messageId"])
check(full.get_message(f["mailboxId"], f["messageId"])["message"]["bodyText"] == f["body"])
scoped.update_mailbox(f["mailboxId"], {displayName: "SDK integration"})
check(full.get_mailbox(f["mailboxId"])["mailbox"]["displayName"] == "SDK integration")
[[-> { scoped.get_account }, 403], [-> { scoped.get_mailbox(f["foreignMailboxId"]) }, 404]].each do |call, status|
  begin
    call.call
    raise "Unauthorized request succeeded"
  rescue Robotomail::ApiError => error
    check(error.status == status)
  end
end
hook = scoped.create_webhook({url: "https://example.com/sdk-fixture", mailboxId: f["mailboxId"], events: ["message.received"]})["webhook"]
full.update_webhook(hook["id"], {headers: nil})
check(full.get_webhook(hook["id"])["webhook"]["headers"].nil?)
full.delete_webhook(hook["id"])
sent = full.send_message(f["mailboxId"], {to: ["delivered@resend.dev"], subject: "Local SDK test", bodyText: "No external email is delivered."})["message"]
check(sent["status"] == "SENT" && sent["externalMessageId"].start_with?("email-mock-"))
check(scoped.get_message(f["mailboxId"], sent["id"])["message"]["subject"] == "Local SDK test")
puts JSON.generate({checks: 12, sentMessageId: sent["id"]})

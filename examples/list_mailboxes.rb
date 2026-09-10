require "robotomail"

mail = Robotomail::Client.new # reads ROBOTOMAIL_API_KEY
mail.list_mailboxes["mailboxes"].each { |box| puts box["fullAddress"] }

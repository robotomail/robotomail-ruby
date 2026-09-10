require "minitest/autorun"
require "open3"
require "json"
require "robotomail"

class ClientTest < Minitest::Test
  CASES = JSON.parse(File.read(File.join(__dir__, "cases.json")))
  @@stdin, @@stdout, @@thread = Open3.popen2("python3", File.join(__dir__, "server.py"))
  BASE = @@stdout.gets.strip
  Minitest.after_run do
    Process.kill("TERM", @@thread.pid)
    @@thread.join
    @@stdin.close
    @@stdout.close
  end

  def client(key = "test-key", **options)
    Robotomail::Client.new(api_key: key, base_url: BASE, **options)
  end

  CASES.each do |fixture|
    define_method("test_contract_#{fixture['id']}") do
      args = fixture["paths"].dup
      args << fixture["body"] unless fixture["body"].nil?
      args << Robotomail::Upload.new(data: "\x00\xffbinary\r\n".b, filename: "sample.bin") if fixture["upload"]
      name = fixture["id"].gsub(/([a-z0-9])([A-Z])/, '\1_\2').downcase
      result = fixture["params"].empty? ? client.public_send(name, *args) : client.public_send(name, *args, params: fixture["params"])
      if fixture["id"] == "streamEvents"
        assert_equal [["evt-1", "message.received", "{\"text\":\n\"héllo\"}"], ["evt-1", "message", "second"], ["evt-2", "reconnect", "{}"]], result.map { |f| [f.id, f.event, f.data] }
      else
        assert_equal fixture["response"], result
      end
    end
  end

  [401, 402, 403, 404, 429, 500].each do |status|
    define_method("test_error_#{status}") do
      error = assert_raises(Robotomail::ApiError) { client("error-#{status}").list_mailboxes }
      assert_equal status, error.status
      assert_equal "FIXTURE_ERROR", error.code
      assert_equal "7", error.headers["retry-after"]
    end
  end

  def test_redirect_and_timeout
    error = assert_raises(Robotomail::ApiError) { client("redirect").send_message("box", {to: ["fixture@example.com"], subject: "fixture", bodyText: "fixture"}) }
    assert_equal 307, error.status
    assert_raises(Net::ReadTimeout) { client("slow", timeout: 0.015).list_mailboxes }
    requests = JSON.parse(Net::HTTP.get(URI(BASE.sub("/v1", "/__requests"))))
    assert_equal 1, requests.count { |r| r["auth"] == "Bearer redirect" }
    refute requests.any? { |r| r["path"] == "/__unexpected" }
  end

  def test_null_empty_zero_and_symbols
    assert_equal({}, client("echo").update_webhook("hook", {})["echo"])
    assert_equal({"headers" => nil}, client("echo").update_webhook("hook", {headers: nil})["echo"])
    assert_equal({"displayName" => ""}, client("echo").update_mailbox("box", {displayName: ""})["echo"])
    assert_equal ["0"], client("echo").list_messages("box", params: {limit: 2, offset: 0})["query"]["offset"]
  end

  def test_signature_verification
    raw, secret = "{\"text\":\"héllo\"}\n", "fixture-secret"
    signature = OpenSSL::HMAC.hexdigest("SHA256", secret, raw)
    assert Robotomail.verify_webhook(raw, signature, secret)
    ["", signature.upcase, "g"*64, signature+"0"].each { |bad| refute Robotomail.verify_webhook(raw, bad, secret) }
    refute Robotomail.verify_webhook(raw.strip, signature, secret)
    refute Robotomail.verify_webhook(raw, signature, "wrong")
  end

  def test_early_stream_exit_and_bad_content
    params = CASES.find { |c| c["id"] == "streamEvents" }["params"]
    client.stream_events(params: params).each { |frame| assert_equal "evt-1", frame.id; break }
    assert_raises(RuntimeError) { client("bad-stream").stream_events(params: params).to_a }
  end

  def test_url_validation
    ["http://example.com/v1", "https://user:pass@example.com/v1", "https://example.com/v1?key=x"].each do |base_url|
      assert_raises(ArgumentError) { Robotomail::Client.new(base_url: base_url) }
    end
    ["", ".", ".."].each { |id| assert_raises(ArgumentError) { client.get_mailbox(id) } }
  end
end

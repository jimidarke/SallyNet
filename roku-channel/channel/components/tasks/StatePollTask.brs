' StatePollTask — fetch /api/state once per control="RUN", post to m.top.snapshot.

sub init()
    m.top.functionName = "runPoll"
end sub

sub runPoll()
    url = snStateUrl()
    t = createObject("roUrlTransfer")
    t.setUrl(url)
    t.setRequest("GET")
    t.setMessagePort(createObject("roMessagePort"))
    t.enableEncodings(true)

    body = t.getToString()
    if body = invalid or body = "" then
        m.top.ok = false
        m.top.snapshot = { err:"empty" }
        return
    end if

    parsed = ParseJson(body)
    if parsed = invalid then
        m.top.ok = false
        m.top.snapshot = { err:"parse" }
        return
    end if

    m.top.ok = true
    m.top.snapshot = parsed
end sub

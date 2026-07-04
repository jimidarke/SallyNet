' SallyNet — shared blocking HTTP JSON GET. Task-thread only (blocks the calling thread).
' Extracted from MediaListTask.brs when StudioListTask needed the identical function.

function httpGetJson(url as string) as object
    t = createObject("roUrlTransfer")
    t.setUrl(url)
    t.setRequest("GET")
    t.setMessagePort(createObject("roMessagePort"))
    t.enableEncodings(true)
    body = t.getToString()
    if body = invalid or body = "" then return invalid
    return ParseJson(body)
end function

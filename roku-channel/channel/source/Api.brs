' SallyNet — API URL builders. Base = registry override (apiBase) else default.
' Override on-device without rebuilding via ECP deep-link ?apiBase=...

function snApiBase() as string
    override = regRead(SN_REG_API_BASE())
    if override <> "" then return override
    return SN_API_BASE_DEFAULT()
end function

function snStateUrl() as string : return snApiBase() + "/api/state" : end function
function snDiscoveryUrl() as string : return snApiBase() + "/api/discovery" : end function
function snMediaUrl(kind as string) as string : return snApiBase() + "/api/media?type=" + kind : end function

' --- home media (P1/P5) --------------------------------------------------
function snMediaTripsUrl() as string : return snMediaUrl("trips") : end function
function snCollectionUrl(id as string) as string : return snApiBase() + "/api/collections/" + id : end function
function snPhotosUrl() as string : return snApiBase() + "/api/photos" : end function
function snQrUrl() as string : return snApiBase() + "/api/qr.png" : end function

' Absolutize a catalog url/poster/thumb that may be root-relative ("/media/..").
function snMediaItemUrl(p as dynamic) as string
    if p = invalid or p = "" then return ""
    if Left(p, 4) = "http" then return p
    return snApiBase() + p
end function

' Ambient map PNG. The server picks centre (live GPS) + zoom (speed band), so the Roku passes
' only its display size and `v` — a cache-buster (the /api/state `ts`) that forces the Poster to
' re-fetch the changed image at this stable URL. The server's render cache ignores `v`.
function snMapUrl(w as integer, h as integer, v as string) as string
    return snApiBase() + "/api/map.png?w=" + w.toStr() + "&h=" + h.toStr() + "&v=" + v
end function

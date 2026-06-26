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

function snMapUrl(w as integer, h as integer, z as integer) as string
    return snApiBase() + "/api/map.png?w=" + w.toStr() + "&h=" + h.toStr() + "&z=" + z.toStr()
end function

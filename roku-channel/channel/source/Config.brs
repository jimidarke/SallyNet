' SallyNet — config / constants / registry / logging / pure helpers.
' BrightScript has no module-scope const, so each token is a function returning
' the literal. Cheap to call, easy to grep. (source/*.brs is global to all components.)

' --- Sunset palette (0xRRGGBBAA) -----------------------------------------
function SN_CREAM()  as string : return "0xFFF8E1FF" : end function
function SN_ALMOND() as string : return "0xE8DCC8FF" : end function
function SN_INK()    as string : return "0x2B2A26FF" : end function
function SN_TEXT()   as string : return "0xFAF6EEFF" : end function
function SN_MUTED()  as string : return "0x2B2A26AA" : end function
function SN_RED()    as string : return "0xC8462EFF" : end function
function SN_ORANGE() as string : return "0xE8702EFF" : end function
function SN_GOLD()   as string : return "0xE8A044FF" : end function
function SN_SKY()    as string : return "0xF6B45AFF" : end function
function SN_OK()     as string : return "0x6B9080FF" : end function
function SN_SCRIM()  as string : return "0x2B2A26E6" : end function

' --- API -----------------------------------------------------------------
function SN_API_BASE_DEFAULT() as string : return "http://192.168.2.216:8090" : end function

' --- Mode hint threshold -------------------------------------------------
' Mirrors sally-api SALLY_DRIVING_KMH (mode is server-derived; this is for any
' client-side display/threshold use). Keep in sync with sallyconf.py.
function SN_DRIVING_KMH() as integer : return 10 : end function

' ETA older than this (seconds) is shown as stale on the Drive screen.
function SN_ETA_STALE_S() as integer : return 600 : end function

' --- Registry ------------------------------------------------------------
function SN_REG_SECTION()    as string  : return "sallynet" : end function
function SN_CACHE_VER()      as integer : return 1 : end function
function SN_REG_API_BASE()   as string  : return "apiBase" : end function
function SN_REG_LAST_STATE() as string  : return "lastStateV1" : end function
function SN_REG_MEDIA_CATALOG() as string : return "mediaCatalogV1" : end function
function SN_REG_PHOTO_CATALOG() as string : return "photoCatalogV1" : end function
function SN_REG_RESUME_PREFIX() as string : return "resume:" : end function   ' resume:<contentid> -> seconds

' --- media UI tunables ---------------------------------------------------
function SN_SLIDESHOW_MS()   as integer : return 6000 : end function
function SN_VOD_WATCHDOG_S() as integer : return 90 : end function

' Reconnect backoff (mirrors HouseWall): 2s, 5s, 10s, 30s…
function snNextBackoffSeconds(attempt as integer) as integer
    if attempt <= 1 then return 2
    if attempt = 2 then return 5
    if attempt = 3 then return 10
    return 30
end function

function regRead(key as string) as string
    section = createObject("roRegistrySection", SN_REG_SECTION())
    if section = invalid then return ""
    if not section.exists(key) then return ""
    return section.read(key)
end function

sub regWrite(key as string, value as string)
    section = createObject("roRegistrySection", SN_REG_SECTION())
    if section = invalid then return
    section.write(key, value)
    section.flush()
end sub

' --- Logging -------------------------------------------------------------
sub slLog(msg as string)
    print "[SallyNet] " + msg
end sub

' Structured one-liner: [SallyNet] event=<name> k=v k=v  (parsed by tests/smoke)
sub slEvent(name as string, kv as object)
    line = "[SallyNet] event=" + name
    if kv <> invalid then
        for each k in kv
            v = kv[k]
            if v = invalid then
                vs = "invalid"
            else
                vs = v.toStr()
            end if
            line = line + " " + k + "=" + snSanitise(vs)
        end for
    end if
    print line
end sub

function snSanitise(s as string) as string
    out = ""
    rest = s
    while true
        idx = Instr(1, rest, " ")
        if idx = 0 then
            out = out + rest
            exit while
        end if
        out = out + Left(rest, idx - 1) + "_"
        rest = Mid(rest, idx + 1)
    end while
    return out
end function

' --- Pure helpers --------------------------------------------------------
function snParseInt(v as dynamic) as integer
    if v = invalid then return 0
    if type(v) = "Integer" or type(v) = "roInt" then return v
    return v.toStr().toInt()
end function

' Float -> "x.y" string; invalid -> "--". Handles negatives.
function snFmt1(v as dynamic) as string
    if v = invalid then return "--"
    n = v
    if type(n) = "String" or type(n) = "roString" then n = Val(n)
    neg = false
    if n < 0 then
        neg = true
        n = -n
    end if
    scaled = Int(n * 10 + 0.5)
    s = (scaled \ 10).toStr() + "." + (scaled mod 10).toStr()
    if neg then s = "-" + s
    return s
end function

' Number -> rounded integer string; invalid -> "--".
function snFmtInt(v as dynamic) as string
    if v = invalid then return "--"
    n = v
    if type(n) = "String" or type(n) = "roString" then n = Val(n)
    if n < 0 then return "-" + Int(-n + 0.5).toStr()
    return Int(n + 0.5).toStr()
end function

function asStr(v as dynamic) as string
    if v = invalid then return "--"
    return v.toStr()
end function

function iif(cond as boolean, a as string, b as string) as string
    if cond then return a
    return b
end function

function pad2(n as integer) as string
    if n < 10 then return "0" + n.toStr()
    return n.toStr()
end function

function snClockHM() as string
    d = createObject("roDateTime")
    d.Mark()
    d.ToLocalTime()
    return pad2(d.GetHours()) + ":" + pad2(d.GetMinutes())
end function

function snClockHMS() as string
    d = createObject("roDateTime")
    d.Mark()
    d.ToLocalTime()
    return pad2(d.GetHours()) + ":" + pad2(d.GetMinutes()) + ":" + pad2(d.GetSeconds())
end function

function snNowSeconds() as integer
    d = createObject("roDateTime")
    d.Mark()
    return d.AsSeconds()
end function

' ISO date ("2026-07-04T..." or "2026-07-04") -> "Jul 4, 2026". Falls back to the
' raw string if it doesn't look like a date.
function snDateLabelFromIso(iso as dynamic) as string
    if iso = invalid then return ""
    s = iso.toStr()
    if Len(s) < 10 then return s
    months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    mi = Mid(s, 6, 2).toInt()
    if mi < 1 or mi > 12 then return s
    return months[mi] + " " + Mid(s, 9, 2).toInt().toStr() + ", " + Mid(s, 1, 4)
end function

' Epoch (UTC seconds, e.g. trip.eta) -> "2h 05m" / "12m" / "now" remaining. Timezone-
' free: works off the delta to the Roku's own clock, so no TZ guessing needed.
function snEtaRemaining(epoch as dynamic) as string
    if epoch = invalid then return "--"
    secs = snParseInt(epoch) - snNowSeconds()
    if secs <= 0 then return "now"
    mins = secs \ 60
    h = mins \ 60
    mm = mins mod 60
    if h > 0 then return h.toStr() + "h " + pad2(mm) + "m"
    return mm.toStr() + "m"
end function

' "YYYY-MM-DD..." start date -> day number of the trip (1-based), 0 if unknown/future.
function snDaysSinceIso(iso as dynamic) as integer
    if iso = invalid then return 0
    s = iso.toStr()
    if Len(s) < 10 then return 0
    d = createObject("roDateTime")
    d.FromISO8601String(Left(s, 10) + "T12:00:00Z")
    startSec = d.AsSeconds()
    if startSec <= 0 then return 0
    diff = snNowSeconds() - startSec
    if diff < 0 then return 0
    return (diff \ 86400) + 1
end function

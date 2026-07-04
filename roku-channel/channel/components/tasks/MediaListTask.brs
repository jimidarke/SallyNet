' MediaListTask — fetch /api/media?type=trips, then each collection's items, and
' /api/photos. Builds the videoCatalog node tree (rows = trips, items = that trip's
' videos AND photos) and publishes the photo catalog. One-shot per control="RUN".

sub init()
    m.top.functionName = "runFetch"
end sub

' httpGetJson() lives in pkg:/source/Http.brs (shared with StudioListTask).

sub runFetch()
    root = createObject("roSGNode", "ContentNode")

    trips = httpGetJson(snMediaTripsUrl())
    if trips <> invalid and trips.collections <> invalid then
        for each c in trips.collections
            durl = snCollectionUrl("")
            if c.detailUrl <> invalid then
                durl = snApiBase() + c.detailUrl
            else if c.id <> invalid then
                durl = snCollectionUrl(c.id)
            end if
            detail = httpGetJson(durl)
            if detail <> invalid and detail.items <> invalid then
                row = invalid
                for each it in detail.items
                    if it.type = "video" and it.url <> invalid then
                        if row = invalid then
                            row = root.createChild("ContentNode")
                            row.title = snRowTitle(c)
                        end if
                        n = row.createChild("ContentNode")
                        if it.title <> invalid then n.title = it.title
                        n.hdPosterUrl = snMediaItemUrl(it.poster)
                        n.shortDescriptionLine1 = snDateLabelFromIso(it.captureDatetime)
                        if c.place <> invalid then n.shortDescriptionLine2 = c.place
                        n.url = snMediaItemUrl(it.url)
                        n.streamFormat = "mp4"
                        if it.durationSec <> invalid then n.length = snParseInt(it.durationSec)
                        if it.id <> invalid then n.id = it.id
                    else if it.type = "photo" and it.url <> invalid then
                        ' Photos share the trip row; no streamFormat -> TripsScreen opens the
                        ' PhotoGallery slideshow instead of VodPlayer on select.
                        if row = invalid then
                            row = root.createChild("ContentNode")
                            row.title = snRowTitle(c)
                        end if
                        n = row.createChild("ContentNode")
                        if it.title <> invalid then n.title = it.title
                        n.hdPosterUrl = snMediaItemUrl(it.poster)
                        n.shortDescriptionLine1 = snDateLabelFromIso(it.captureDatetime)
                        if c.place <> invalid then n.shortDescriptionLine2 = c.place
                        n.url = snMediaItemUrl(it.url)
                        if it.id <> invalid then n.id = it.id
                    end if
                end for
            end if
        end for
    end if
    m.top.videoCatalog = root

    photos = httpGetJson(snPhotosUrl())
    if photos = invalid or photos.photos = invalid then photos = { photos: [] }
    m.top.photoCatalog = photos

    m.top.ok = true
    slEvent("media_catalog", { rows: root.getChildCount(), photos: photos.photos.count() })
end sub

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/Users/erinckoc/Desktop/logistic document.webp")
OUTPUT = ROOT / "samples" / "filled_bill_of_lading.png"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = "/System/Library/Fonts/HelveticaNeue.ttc"
    index = 1 if bold else 0
    return ImageFont.truetype(path, size=size, index=index)


def draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int = 22) -> None:
    draw.text(xy, text, fill="black", font=font(size))


def draw_multiline(draw: ImageDraw.ImageDraw, xy: tuple[int, int], lines: list[str], size: int = 22, gap: int = 43) -> None:
    x, y = xy
    for line in lines:
        draw_text(draw, (x, y), line, size=size)
        y += gap


def main() -> None:
    img = Image.open(SOURCE).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Header
    draw_text(draw, (145, 185), "2026-05-15", 22)
    draw_text(draw, (1485, 190), "1", 24)

    # Ship from
    draw_multiline(
        draw,
        (240, 292),
        [
            "Anatolia Export GmbH",
            "Mergenthalerallee 15",
            "65760 Eschborn, DE",
            "SID-DE-448219",
        ],
    )
    draw_text(draw, (830, 405), "X", 24)

    # Bill / carrier
    draw_text(draw, (1345, 312), "BOL-2026-0515-0007", 22)
    draw_text(draw, (1270, 470), "Rhine Freight Logistics", 22)
    draw_text(draw, (1220, 515), "TR-58291", 22)
    draw_text(draw, (1220, 560), "SEAL-77429", 22)
    draw_text(draw, (960, 662), "RFLG", 22)
    draw_text(draw, (1040, 705), "PRO-839201", 22)

    # Ship to
    draw_multiline(
        draw,
        (240, 483),
        [
            "Bosphorus Retail A.S.",
            "Orhanli Mah. Lojistik Cad. 8",
            "34956 Tuzla, Istanbul, TR",
            "CID-TR-991204",
        ],
    )
    draw_text(draw, (810, 492), "IST-DC-04", 22)

    # Third-party billing and instructions
    draw_multiline(
        draw,
        (240, 695),
        [
            "EuroTrade Finance Services",
            "Mainzer Landstrasse 50",
            "60325 Frankfurt am Main, DE",
        ],
    )
    draw_multiline(
        draw,
        (95, 900),
        [
            "Keep dry. Do not stack more than 2 pallets high.",
            "Notify consignee 24 hours before delivery.",
        ],
        size=21,
        gap=32,
    )

    # Freight terms
    draw_text(draw, (1150, 848), "X", 24)

    # Customer order information
    rows = [
        ("PO-78451", "8", "1,120 kg", "Y", "Automotive spare parts"),
        ("PO-78452", "6", "860 kg", "Y", "Textile cartons"),
        ("PO-78453", "4", "540 kg", "N", "Packaging materials"),
    ]
    y = 1042
    for order, pkgs, weight, pallet, info in rows:
        draw_text(draw, (145, y), order, 20)
        draw_text(draw, (615, y), pkgs, 20)
        draw_text(draw, (775, y), weight, 20)
        draw_text(draw, (945, y), "X" if pallet == "Y" else "", 20)
        draw_text(draw, (1032, y), "X" if pallet == "N" else "", 20)
        draw_text(draw, (1160, y), info, 20)
        y += 42
    draw_text(draw, (615, 1340), "18", 22)
    draw_text(draw, (770, 1340), "2,520 kg", 22)

    # Carrier information
    draw_text(draw, (105, 1535), "18", 20)
    draw_text(draw, (210, 1535), "PALLET", 18)
    draw_text(draw, (350, 1535), "18", 20)
    draw_text(draw, (465, 1535), "CTN", 20)
    draw_text(draw, (570, 1535), "2,520 kg", 20)
    draw_text(draw, (735, 1535), "N", 20)
    draw_text(draw, (825, 1535), "MIXED CONSUMER GOODS - NON HAZARDOUS", 20)
    draw_text(draw, (1480, 1535), "156600", 20)
    draw_text(draw, (1645, 1535), "70", 20)

    draw_text(draw, (570, 1888), "2,520 kg", 20)
    draw_text(draw, (1155, 1950), "0.00", 22)
    draw_text(draw, (1540, 2155), "X", 22)
    draw_text(draw, (1682, 2205), "X", 22)

    # Signatures / loading details
    draw_text(draw, (185, 2420), "E. Demir / 2026-05-15", 20)
    draw_text(draw, (690, 2350), "X", 22)
    draw_text(draw, (920, 2350), "X", 22)
    draw_text(draw, (1320, 2420), "M. Keller / 2026-05-15", 20)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()

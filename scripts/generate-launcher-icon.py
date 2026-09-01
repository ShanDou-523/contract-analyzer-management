"""Generate the contract analysis launcher icon in PNG and Windows ICO formats."""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"
CANVAS_SIZE = 1024


def build_icon() -> Image.Image:
    image = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Restrained business palette: deep green, warm paper, gold, and a red risk marker.
    draw.rounded_rectangle((48, 48, 976, 976), radius=190, fill="#173D37")
    draw.rounded_rectangle((88, 88, 936, 936), radius=160, outline="#2D5A51", width=16)

    document = (242, 170, 748, 846)
    draw.rounded_rectangle(document, radius=52, fill="#F7F5ED")
    draw.polygon(((620, 170), (748, 298), (620, 298)), fill="#D9E1DB")
    draw.line(((620, 170), (620, 298), (748, 298)), fill="#B8C7BF", width=12)

    draw.rounded_rectangle((316, 344, 656, 376), radius=16, fill="#315E55")
    draw.rounded_rectangle((316, 426, 610, 452), radius=13, fill="#8AA098")
    draw.rounded_rectangle((316, 490, 574, 516), radius=13, fill="#8AA098")
    draw.rounded_rectangle((316, 554, 530, 580), radius=13, fill="#8AA098")

    # Analysis lens.
    draw.ellipse((550, 532, 862, 844), fill="#F7F5ED", outline="#D7A942", width=36)
    draw.line(((780, 786), (892, 898)), fill="#D7A942", width=72)
    draw.ellipse((626, 606, 786, 766), fill="#173D37")

    # Verified-contract check and a small risk indicator.
    draw.line(((654, 686), (698, 730), (770, 644)), fill="#F7F5ED", width=34, joint="curve")
    draw.ellipse((206, 708, 342, 844), fill="#C2574B", outline="#F7F5ED", width=18)
    draw.rounded_rectangle((264, 742, 284, 796), radius=10, fill="#F7F5ED")
    draw.ellipse((263, 810, 285, 832), fill="#F7F5ED")
    return image


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    icon = build_icon()
    icon.save(ASSET_DIR / "contract-analysis-launcher.png")
    icon.save(
        ASSET_DIR / "contract-analysis.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    main()

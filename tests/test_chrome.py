"""Tests for window chrome styles."""

from PIL import Image

from agent_log_gif.chrome import ChromeStyle, get_corner_radius, get_titlebar_height
from agent_log_gif.renderer import TerminalRenderer
from agent_log_gif.theme import TerminalTheme


class TestChromeProperties:
    def test_enum_values(self):
        assert ChromeStyle.NONE == "none"
        assert ChromeStyle.MAC == "mac"
        assert ChromeStyle.MAC_SQUARE == "mac-square"
        assert ChromeStyle.WINDOWS == "windows"
        assert ChromeStyle.LINUX == "linux"

    def test_enum_from_string(self):
        assert ChromeStyle("mac") == ChromeStyle.MAC
        assert ChromeStyle("none") == ChromeStyle.NONE
        assert ChromeStyle("mac-square") == ChromeStyle.MAC_SQUARE

    def test_titlebar_height_none_is_zero(self):
        assert get_titlebar_height(ChromeStyle.NONE) == 0

    def test_titlebar_height_styles_are_positive(self):
        for style in (
            ChromeStyle.MAC,
            ChromeStyle.MAC_SQUARE,
            ChromeStyle.WINDOWS,
            ChromeStyle.LINUX,
        ):
            assert get_titlebar_height(style) > 0

    def test_corner_radius_none_is_zero(self):
        assert get_corner_radius(ChromeStyle.NONE) == 0

    def test_corner_radius_mac_square_is_zero(self):
        assert get_corner_radius(ChromeStyle.MAC_SQUARE) == 0

    def test_corner_radius_rounded_styles(self):
        for style in (ChromeStyle.MAC, ChromeStyle.WINDOWS, ChromeStyle.LINUX):
            assert get_corner_radius(style) > 0


class TestRendererChrome:
    def test_default_chrome_is_mac(self):
        renderer = TerminalRenderer(TerminalTheme(cols=40, rows=10))
        assert renderer.chrome == ChromeStyle.MAC

    def test_none_chrome_produces_shorter_image(self):
        theme = TerminalTheme(cols=40, rows=10)
        mac = TerminalRenderer(theme, chrome=ChromeStyle.MAC)
        none_ = TerminalRenderer(theme, chrome=ChromeStyle.NONE)
        assert none_.image_height < mac.image_height
        assert none_.image_width == mac.image_width

    def test_all_chrome_styles_render_valid_images(self):
        theme = TerminalTheme(cols=40, rows=10)
        lines = [[("Hello", "#F8F8F2")]]
        for style in ChromeStyle:
            renderer = TerminalRenderer(theme, chrome=style)
            frame = renderer.render_frame(lines)
            assert isinstance(frame, Image.Image)
            assert frame.size == (renderer.image_width, renderer.image_height)

    def test_different_chrome_styles_produce_different_images(self):
        theme = TerminalTheme(cols=40, rows=10)
        lines = [[("Hello", "#F8F8F2")]]
        images = {}
        for style in ChromeStyle:
            renderer = TerminalRenderer(theme, chrome=style)
            images[style] = renderer.render_frame(lines).tobytes()

        # Each style with a titlebar should produce visually distinct output
        styled = [s for s in ChromeStyle if s != ChromeStyle.NONE]
        for i, a in enumerate(styled):
            for b in styled[i + 1 :]:
                assert images[a] != images[b], f"{a} and {b} produced identical images"

    def test_none_chrome_top_pixel_is_background(self):
        theme = TerminalTheme(cols=40, rows=10, background="#282A36")
        renderer = TerminalRenderer(theme, chrome=ChromeStyle.NONE)
        frame = renderer.render_frame([])
        top_pixel = frame.getpixel((frame.width // 2, 2))
        assert top_pixel == (40, 42, 54)  # #282A36

    def test_mac_square_has_square_corners(self):
        """mac-square corner pixel should differ from mac (which has rounded corners)."""
        theme = TerminalTheme(cols=40, rows=10)
        mac = TerminalRenderer(theme, chrome=ChromeStyle.MAC)
        square = TerminalRenderer(theme, chrome=ChromeStyle.MAC_SQUARE)

        mac_frame = mac.render_frame([])
        square_frame = square.render_frame([])

        # Top-left corner: mac has rounded corner (bg color), square has titlebar color
        mac_corner = mac_frame.getpixel((0, 0))
        square_corner = square_frame.getpixel((0, 0))
        assert mac_corner != square_corner

    def test_mac_and_mac_square_share_traffic_lights(self):
        """Both mac styles should have traffic lights (same pixels in the dot area)."""
        theme = TerminalTheme(cols=40, rows=10)
        mac = TerminalRenderer(theme, chrome=ChromeStyle.MAC)
        square = TerminalRenderer(theme, chrome=ChromeStyle.MAC_SQUARE)

        mac_frame = mac.render_frame([])
        square_frame = square.render_frame([])

        # Sample a pixel where the first traffic light dot (red) should be
        # Traffic light center: x=18, y=18 at 1x
        dot_pixel_mac = mac_frame.getpixel((18, 18))
        dot_pixel_square = square_frame.getpixel((18, 18))
        assert dot_pixel_mac == dot_pixel_square

    def test_mac_can_use_custom_canvas_background(self):
        theme = TerminalTheme(cols=40, rows=10, background="#282A36")
        renderer = TerminalRenderer(
            theme,
            chrome=ChromeStyle.MAC,
            canvas_background="#FFFFFF",
        )

        frame = renderer.render_frame([])

        assert frame.getpixel((0, 0)) == (255, 255, 255)
        assert frame.getpixel((frame.width // 2, renderer.image_height - 2)) == (
            40,
            42,
            54,
        )
        assert frame.getpixel((0, frame.height - 1)) == (255, 255, 255)
        assert frame.getpixel((frame.width - 1, frame.height - 1)) == (
            255,
            255,
            255,
        )

    def test_canvas_background_is_ignored_for_mac_square(self):
        theme = TerminalTheme(cols=40, rows=10, background="#282A36")
        default_renderer = TerminalRenderer(
            theme,
            chrome=ChromeStyle.MAC_SQUARE,
        )
        renderer = TerminalRenderer(
            theme,
            chrome=ChromeStyle.MAC_SQUARE,
            canvas_background="#FFFFFF",
        )

        default_frame = default_renderer.render_frame([])
        frame = renderer.render_frame([])

        assert frame.getpixel((0, 0)) == default_frame.getpixel((0, 0))
        assert frame.getpixel((0, frame.height - 1)) == default_frame.getpixel(
            (0, frame.height - 1)
        )

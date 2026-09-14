# Brand images

Home Assistant 2026.3 and newer serve brand images from this folder, and local
files take priority over the central brands CDN. Nothing is shipped here on
purpose: the Sharp NEC marks belong to Sharp NEC Display Solutions, and this
project does not redistribute them.

Drop your own files in this folder and they appear on the integration page
after a restart.

| File | Size | Required |
| --- | --- | --- |
| `icon.png` | 256 x 256 | yes |
| `icon@2x.png` | 512 x 512 | yes |
| `logo.png` | any aspect ratio | no |
| `logo@2x.png` | twice the `logo.png` dimensions | no |

Requirements, following the Home Assistant brands image specification:

- PNG only. A URL to an image elsewhere on the web cannot be used; Home
  Assistant serves these files from disk.
- The icon must be square (1:1). Leave out the logo files and the icon is used
  as the logo as well.
- Transparency is preferred, and the image should be trimmed so there is no
  empty space around the subject.
- Variants optimised for a dark background may be prefixed with `dark_`.
- Do not use Home Assistant branded images here.

Manufacturer press kits are usually the best source. Whether you may use a
manufacturer's mark is between you and that manufacturer.

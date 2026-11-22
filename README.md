# LoamLab — Soil Testing Appointment & Report Access Portal

A Flask + SQLite recreation based on the supplied reference screenshots and the two reference screen-recordings. It includes separate customer and laboratory-admin portals, sample tracking, an operations queue, report data entry, supporting-file uploads, and branded PDF report generation.

## What changed in this version
**Website (matches the reference videos)**
- Single-page home with the sections shown in the videos: hero with farmland background and "soil core" glass card, interactive Strata diagnostics, 5-stage Process flow, Diagnostics cards, Soil Health Quick Assessment, dual-portal image cards and a copper outlined LOAMLAB footer wordmark. Header links (Strata / Process / Diagnostics / Portal) scroll smoothly and highlight the active section.
- Transitions & animation (`static/app.js` + `static/style.css`): headline "ghost-trail" reveal, staggered card fade-ups, the outgoing section dims and blurs as the next one arrives, page-to-page fade, animated process line and node pings, stage-tracker nodes lighting in sequence, animated pH gradient marker and N-P-K bars, wordmark stroke-draw. All motion is disabled automatically for visitors who prefer reduced motion.
- Split-screen login/register with a soil image, customer dashboard with horizontal stage trackers and result bars, lab queue with metric cards, filter chips, one-click "advance to next stage"; customers can cancel while a request is still *Requested*.
- Quick Assessment only suggests a **booking panel** (indicative guidance); it never diagnoses.

**PDF report (`report_pdf.py`) - rebuilt**
- Fixed grid: A4 with 16 mm margins; every table sums to exactly 178 mm so all columns align.
- Branded first-page header band, slim running header, footer with report number, generated time and *Page X of Y*.
- Summary strip, numbered sections, right-aligned values, a "Position" column (a plain numeric comparison of the lab's own value against the lab's own interval, when that interval can be read as a range such as `6.0 - 7.5`, `> 22` or `< 0.5`).
- pH 0-14 scale with marker; bar charts only compare parameters that share a unit.
- Interpretation, recommendations, method notes, authorization block with signature/stamp box, scope & limitations. Headings are never stranded at a page bottom; long tables repeat their header row.

## Images
`static/img/*.jpg` are original generated artwork (no stock photos). To use real photographs, replace the files keeping the same names (hero-field.jpg, soil-hand.jpg, lab-beakers.jpg, lab-growlight.jpg). `python tools/make_images.py` regenerates the originals (needs pillow + numpy).

## Preview with demo data (optional)
`python seed_demo.py` adds demo customers, bookings and two reports so you can see the dashboard, queue and PDF. **All values are placeholders for layout testing, not real measurements.** Customer login: `farmer@loamlab.local` / `Farmer@123`. Delete `data/loamlab.sqlite3` to remove it. Set `LOAMLAB_DEMO=0` to hide the tap-to-fill demo sign-in buttons.

## Non-English text in the PDF (e.g. Kannada)
The built-in PDF fonts only cover Latin characters. Put `Report-Regular.ttf` and `Report-Bold.ttf` (any Unicode font containing the script you need, such as Noto Sans Kannada) into the `fonts/` folder and the report will use them automatically.

## Run on Windows
1. Extract this ZIP.
2. Open the `loamlab_v2` folder in VS Code.
3. Install Python 3.10 or newer.
4. In PowerShell run `Set-ExecutionPolicy -Scope Process Bypass` if your machine blocks activation scripts (the batch launcher activates its own environment).
5. Double-click `run_windows.bat`, or run ` .\run_windows.bat` from PowerShell.
6. Open http://127.0.0.1:5000.

## Demo administrator
- URL: http://127.0.0.1:5000/login (choose “Lab Admin”)
- Email: `admin@loamlab.local`
- Password: `LabAdmin@123`

Change the demo password and set a strong random `SECRET_KEY` before deployment. The demo administrator is created in a fresh local database on first run.

## Customer workflow
- Create an account at `/register`.
- Sign in at `/login` and choose “Customer”.
- Book a soil test and use My Soil Tests to follow the booking.
- When the lab releases a report, the customer can download the PDF from the appointment details.

## Laboratory workflow
- Sign in at `/login` and choose “Lab Admin”.
- Use the Sample Queue to search/filter appointments.
- Open a booking to update its stage and add a customer-visible note.
- Enter only measured laboratory values, method-specific reference intervals, interpretation and recommendations. Upload an optional lab worksheet or certificate.
- Save results and download the generated PDF preview. The report is available to the associated customer.

## PDF report contents
Branded LoamLab title and report identifiers; customer/sample particulars; sample receipt and testing dates; measured results and units; lab-entered reference intervals; a numeric-value comparison graphic (only for numeric values); interpretation; recommendations; analyst authorization fields; and scope/limitations language.

**Scientific integrity:** the system does not create or guess soil measurements, interpretations, or fertilizer recommendations. Blank parameters are omitted. Default guidance labels explicitly state that ranges depend on the analytical method/crop/region; the laboratory should enter its validated reference interval. The chart is only a relative visual comparison of values with different units, not a fertility score. This PDF is a portal-generated result summary, not an accredited/statutory certificate unless authorized and issued by a qualified laboratory.

## Data and storage
- SQLite database: `data/loamlab.sqlite3`
- Uploaded lab attachments: `uploads/`
- Generated reports are streamed as PDFs; they are not permanently archived by default.
- Back up the `data/` and `uploads/` folders regularly. Do not delete them when updating application code.

## Security / production notes
Passwords are hashed. Customer report and appointment routes enforce ownership checks; administrator functions require the admin role. This is a local prototype, not a production-hardened deployment. Before public hosting, add CSRF protection, rate limiting, email verification/password reset, HTTPS, secure secret management, audit-log retention policy, malware scanning for uploaded files, database backups, and a qualified laboratory review/sign-off process. Consider PostgreSQL for multi-user production hosting.

## Original visual reference
`assets/original_reference_screenshots.zip` contains the screenshots supplied for this recreation.

## Author
Built by Prasanna as part of the College Project journey.

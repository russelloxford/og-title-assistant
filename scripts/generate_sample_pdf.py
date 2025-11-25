"""
Generate sample PDF documents for testing the splitter.

This script creates test PDFs that simulate oil & gas legal documents
with body content and exhibit sections.
"""

import fitz  # PyMuPDF
from pathlib import Path


def create_sample_assignment_pdf(output_path: str, num_lease_pages: int = 10) -> str:
    """
    Create a sample Assignment document with exhibits.

    Structure:
    - Pages 1-5: Document body (assignment language)
    - Page 6+: Exhibit A - Schedule of Leases (table format)

    Args:
        output_path: Path for the output PDF
        num_lease_pages: Number of pages for the lease schedule

    Returns:
        Path to the created PDF
    """
    doc = fitz.open()

    # Page dimensions (Letter size)
    width, height = 612, 792
    margin = 72  # 1 inch

    # === BODY PAGES (1-5) ===

    # Page 1: Title and parties
    page = doc.new_page(width=width, height=height)
    page.insert_text(
        (margin, margin + 50),
        "ASSIGNMENT OF OIL AND GAS LEASES",
        fontsize=16,
        fontname="helv",
    )
    page.insert_text(
        (margin, margin + 100),
        "STATE OF NORTH DAKOTA",
        fontsize=12,
    )
    page.insert_text(
        (margin, margin + 120),
        "COUNTY OF WILLIAMS",
        fontsize=12,
    )
    page.insert_text(
        (margin, margin + 160),
        "KNOW ALL MEN BY THESE PRESENTS:",
        fontsize=11,
    )
    body_text = """
    That SMITH OIL COMPANY, LLC, a Delaware limited liability company
    ("Assignor"), for and in consideration of TEN DOLLARS ($10.00) and
    other good and valuable consideration, the receipt and sufficiency
    of which are hereby acknowledged, does hereby GRANT, BARGAIN, SELL,
    ASSIGN, TRANSFER, SET OVER and DELIVER unto JONES ENERGY PARTNERS,
    LP, a Texas limited partnership ("Assignee"), all of Assignor's
    right, title and interest in and to the oil and gas leases
    described in Exhibit A attached hereto and made a part hereof.
    """
    page.insert_textbox(
        fitz.Rect(margin, margin + 200, width - margin, height - margin),
        body_text,
        fontsize=11,
    )

    # Page 2: Terms and conditions
    page = doc.new_page(width=width, height=height)
    terms_text = """
    TERMS AND CONDITIONS

    1. RESERVATIONS: Assignor reserves unto itself, its successors and
    assigns, an overriding royalty interest equal to one-sixteenth
    (1/16th) of 8/8ths of all oil, gas and other minerals produced and
    saved from the lands covered by the Leases.

    2. WARRANTY: Assignor warrants that it is the lawful owner of the
    interests herein assigned and that such interests are free and clear
    of all liens, encumbrances and claims whatsoever.

    3. PROPORTIONATE REDUCTION: If Assignor owns less than the full
    leasehold estate in any of the Leases, then the interest assigned
    herein shall be proportionately reduced.

    4. FURTHER ASSURANCES: Assignor agrees to execute such additional
    instruments as may be reasonably necessary to carry out the intent
    and purpose of this Assignment.
    """
    page.insert_textbox(
        fitz.Rect(margin, margin + 50, width - margin, height - margin),
        terms_text,
        fontsize=11,
    )

    # Page 3: More legal language
    page = doc.new_page(width=width, height=height)
    legal_text = """
    5. INDEMNIFICATION: Each party shall indemnify, defend and hold
    harmless the other party from and against any and all claims,
    demands, losses, costs and expenses arising out of the operations
    conducted by the indemnifying party on the Leases.

    6. GOVERNING LAW: This Assignment shall be governed by and construed
    in accordance with the laws of the State of North Dakota.

    7. SUCCESSORS AND ASSIGNS: This Assignment shall be binding upon and
    inure to the benefit of the parties hereto and their respective
    successors and assigns.

    8. ENTIRE AGREEMENT: This Assignment constitutes the entire agreement
    between the parties with respect to the subject matter hereof and
    supersedes all prior negotiations, representations, warranties and
    agreements between the parties.
    """
    page.insert_textbox(
        fitz.Rect(margin, margin + 50, width - margin, height - margin),
        legal_text,
        fontsize=11,
    )

    # Page 4: Execution block
    page = doc.new_page(width=width, height=height)
    page.insert_text(
        (margin, margin + 50),
        "EXECUTED this 15th day of January, 2024.",
        fontsize=11,
    )
    page.insert_text(
        (margin, margin + 120),
        "ASSIGNOR:",
        fontsize=11,
    )
    page.insert_text(
        (margin, margin + 150),
        "SMITH OIL COMPANY, LLC",
        fontsize=11,
    )
    page.insert_text(
        (margin, margin + 180),
        "By: _________________________",
        fontsize=11,
    )
    page.insert_text(
        (margin + 30, margin + 200),
        "John Smith, Manager",
        fontsize=10,
    )
    page.insert_text(
        (margin, margin + 270),
        "ASSIGNEE:",
        fontsize=11,
    )
    page.insert_text(
        (margin, margin + 300),
        "JONES ENERGY PARTNERS, LP",
        fontsize=11,
    )
    page.insert_text(
        (margin, margin + 330),
        "By: _________________________",
        fontsize=11,
    )
    page.insert_text(
        (margin + 30, margin + 350),
        "Mary Jones, General Partner",
        fontsize=10,
    )

    # Page 5: Notary block
    page = doc.new_page(width=width, height=height)
    notary_text = """
    STATE OF NORTH DAKOTA    )
                             ) ss.
    COUNTY OF WILLIAMS       )

    Before me, the undersigned, a Notary Public in and for said County
    and State, on this 15th day of January, 2024, personally appeared
    John Smith, to me known to be the Manager of SMITH OIL COMPANY, LLC,
    and acknowledged that he executed the foregoing instrument as his
    free and voluntary act and deed and as the free and voluntary act
    and deed of said limited liability company.



    ________________________________
    Notary Public

    My Commission Expires: ___________

    [SEAL]
    """
    page.insert_textbox(
        fitz.Rect(margin, margin + 50, width - margin, height - margin),
        notary_text,
        fontsize=11,
    )

    # === EXHIBIT A - SCHEDULE OF LEASES ===

    # First exhibit page with header
    page = doc.new_page(width=width, height=height)
    page.insert_text(
        (width / 2 - 50, margin + 30),
        "EXHIBIT A",
        fontsize=14,
        fontname="helv",
    )
    page.insert_text(
        (width / 2 - 80, margin + 55),
        "SCHEDULE OF LEASES",
        fontsize=12,
        fontname="helv",
    )

    # Table header
    y_pos = margin + 100
    page.insert_text((margin, y_pos), "LESSOR", fontsize=9, fontname="helv")
    page.insert_text((margin + 120, y_pos), "LESSEE", fontsize=9, fontname="helv")
    page.insert_text((margin + 240, y_pos), "RECORDING", fontsize=9, fontname="helv")
    page.insert_text((margin + 340, y_pos), "LANDS", fontsize=9, fontname="helv")

    # Draw header line
    page.draw_line((margin, y_pos + 5), (width - margin, y_pos + 5))

    # Sample lease entries
    leases = [
        ("Smith, John", "Acme Oil Co", "Bk 450/Pg 1", "NW/4 Sec 15-154N-97W"),
        ("Jones, Mary", "Acme Oil Co", "Bk 450/Pg 5", "SW/4 Sec 15-154N-97W"),
        ("Brown, Robert", "Acme Oil Co", "Bk 451/Pg 12", "NE/4 Sec 15-154N-97W"),
        ("Davis, Susan", "Acme Oil Co", "Bk 451/Pg 45", "SE/4 Sec 15-154N-97W"),
        ("Wilson, James", "Acme Oil Co", "Bk 452/Pg 1", "N/2 Sec 16-154N-97W"),
    ]

    y_pos += 20
    for lessor, lessee, recording, lands in leases:
        page.insert_text((margin, y_pos), lessor, fontsize=8)
        page.insert_text((margin + 120, y_pos), lessee, fontsize=8)
        page.insert_text((margin + 240, y_pos), recording, fontsize=8)
        page.insert_text((margin + 340, y_pos), lands, fontsize=8)
        y_pos += 15

    # Additional exhibit pages with more leases
    for page_num in range(num_lease_pages - 1):
        page = doc.new_page(width=width, height=height)
        page.insert_text(
            (width / 2 - 50, margin + 30),
            f"EXHIBIT A (continued)",
            fontsize=10,
        )

        y_pos = margin + 70
        page.insert_text((margin, y_pos), "LESSOR", fontsize=9, fontname="helv")
        page.insert_text((margin + 120, y_pos), "LESSEE", fontsize=9, fontname="helv")
        page.insert_text((margin + 240, y_pos), "RECORDING", fontsize=9, fontname="helv")
        page.insert_text((margin + 340, y_pos), "LANDS", fontsize=9, fontname="helv")
        page.draw_line((margin, y_pos + 5), (width - margin, y_pos + 5))

        y_pos += 20
        for i in range(30):  # ~30 entries per page
            lease_num = page_num * 30 + i + 6
            page.insert_text((margin, y_pos), f"Owner {lease_num}", fontsize=8)
            page.insert_text((margin + 120, y_pos), "Acme Oil Co", fontsize=8)
            page.insert_text((margin + 240, y_pos), f"Bk {450 + lease_num}/Pg {i + 1}", fontsize=8)
            page.insert_text((margin + 340, y_pos), f"Sec {(lease_num % 36) + 1}-154N-97W", fontsize=8)
            y_pos += 15
            if y_pos > height - margin:
                break

    # Save the document
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    doc.close()

    return str(output_path)


def create_simple_deed_pdf(output_path: str) -> str:
    """
    Create a simple deed document (no exhibits).

    Args:
        output_path: Path for the output PDF

    Returns:
        Path to the created PDF
    """
    doc = fitz.open()
    width, height = 612, 792
    margin = 72

    # Page 1: Deed
    page = doc.new_page(width=width, height=height)
    page.insert_text(
        (width / 2 - 80, margin + 50),
        "WARRANTY DEED",
        fontsize=16,
        fontname="helv",
    )

    deed_text = """
    STATE OF NORTH DAKOTA
    COUNTY OF WILLIAMS

    KNOW ALL MEN BY THESE PRESENTS:

    That JOHN DOE and JANE DOE, husband and wife, Grantors, for and in
    consideration of the sum of TEN DOLLARS ($10.00) and other good and
    valuable consideration, do hereby GRANT, BARGAIN, SELL and CONVEY
    unto SMITH FAMILY TRUST, Grantee, the following described real
    property situated in Williams County, North Dakota:

    The Northwest Quarter (NW/4) of Section 15, Township 154 North,
    Range 97 West of the Fifth Principal Meridian, Williams County,
    North Dakota, containing 160 acres, more or less.

    TO HAVE AND TO HOLD the same, together with all and singular the
    appurtenances thereunto belonging or in anywise appertaining, and
    all the estate, right, title, interest, claim and demand whatsoever
    of the Grantors, either in law or equity, of, in and to the above
    bargained premises, with the hereditaments and appurtenances.

    EXECUTED this 1st day of March, 2024.


    ________________________________
    JOHN DOE


    ________________________________
    JANE DOE
    """
    page.insert_textbox(
        fitz.Rect(margin, margin + 80, width - margin, height - margin),
        deed_text,
        fontsize=11,
    )

    # Page 2: Notary
    page = doc.new_page(width=width, height=height)
    notary_text = """
    STATE OF NORTH DAKOTA    )
                             ) ss.
    COUNTY OF WILLIAMS       )

    Before me, the undersigned, a Notary Public in and for said County
    and State, on this 1st day of March, 2024, personally appeared
    JOHN DOE and JANE DOE, husband and wife, to me known to be the
    persons described in and who executed the foregoing instrument, and
    acknowledged that they executed the same as their free and voluntary
    act and deed.

    IN WITNESS WHEREOF, I have hereunto set my hand and official seal
    the day and year last above written.



    ________________________________
    Notary Public

    My Commission Expires: ___________

    [SEAL]
    """
    page.insert_textbox(
        fitz.Rect(margin, margin + 50, width - margin, height - margin),
        notary_text,
        fontsize=11,
    )

    # Save
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    doc.close()

    return str(output_path)


if __name__ == "__main__":
    import sys

    output_dir = Path(__file__).parent.parent / "test_documents"
    output_dir.mkdir(exist_ok=True)

    # Generate sample documents
    print("Generating sample test documents...")

    # Assignment with exhibits
    assignment_path = create_sample_assignment_pdf(
        str(output_dir / "sample_assignment.pdf"),
        num_lease_pages=5,
    )
    print(f"Created: {assignment_path}")

    # Simple deed (no exhibits)
    deed_path = create_simple_deed_pdf(str(output_dir / "sample_deed.pdf"))
    print(f"Created: {deed_path}")

    print("\nDone! Test documents created in:", output_dir)

"""Seed the database with realistic sample legal documents and change history."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from app.config import settings

_EMBEDDINGS_PATH = Path(__file__).parent / "seed_embeddings.json"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Document content (final versions, after all redline changes applied)
# ---------------------------------------------------------------------------

NDA_CONTENT = """\
<strong>MUTUAL NON-DISCLOSURE AGREEMENT</strong>

This Mutual Non-Disclosure Agreement (the "<u>Agreement</u>") is entered into as of January 15, 2025 \
(the "<u>Effective Date</u>") by and between Acme Corporation, a Delaware corporation with its principal \
place of business at 100 Innovation Drive, Wilmington, DE 19801 ("Acme"), and GlobalTech Industries, \
a California corporation with its principal place of business at 2500 Technology Parkway, San Jose, \
CA 95134 ("GlobalTech"). Acme and GlobalTech are each referred to herein as a "Party" and collectively \
as the "Parties."

<strong>RECITALS</strong>

WHEREAS, the Parties wish to explore a potential business relationship (the "<u>Purpose</u>") and, in \
connection therewith, each Party may disclose to the other certain confidential and proprietary \
information; and

WHEREAS, the Parties desire to establish the terms and conditions under which such confidential \
information will be disclosed and protected;

NOW, THEREFORE, in consideration of the mutual covenants and agreements set forth herein, and for \
other good and valuable consideration, the receipt and sufficiency of which are hereby acknowledged, \
the Parties agree as follows:

<strong>1. DEFINITION OF CONFIDENTIAL INFORMATION</strong>

"<u>Confidential Information</u>" means any and all non-public, proprietary, or confidential information \
disclosed by either Party (the "<u>Disclosing Party</u>") to the other Party (the "<u>Receiving Party</u>"), \
whether disclosed orally, in writing, electronically, or by inspection of tangible objects, \
including but not limited to: (a) trade secrets, inventions, ideas, processes, computer source and \
object code, data, formulae, programs, prototypes, and other works of authorship; (b) information \
regarding plans for research, development, new products, marketing and selling, business plans, \
budgets and unpublished financial statements, licenses, prices, costs, and suppliers; (c) information \
regarding the skills and compensation of employees, contractors, and consultants of the Disclosing \
Party; and (d) the existence and terms of this Agreement.

Confidential Information <em>shall not</em> include information that: (i) is or becomes publicly available \
through no fault of the Receiving Party; (ii) was rightfully in the Receiving Party's possession \
prior to disclosure by the Disclosing Party; (iii) is independently developed by the Receiving Party \
without use of the Disclosing Party's Confidential Information; or (iv) is rightfully obtained by \
the Receiving Party from a third party without restriction on disclosure.

<strong>2. OBLIGATIONS OF THE RECEIVING PARTY</strong>

The Receiving Party agrees to: (a) hold the Confidential Information in strict confidence and <em>not \
disclose</em> it to any third party without the prior written consent of the Disclosing Party; (b) use \
the Confidential Information solely for the Purpose; (c) protect the Confidential Information using \
at least the same degree of care it uses to protect its own confidential information, but in no event \
less than reasonable care; and (d) limit access to the Confidential Information to those of its \
employees, officers, directors, consultants, and advisors who have a need to know such information \
for the Purpose and who are bound by confidentiality obligations no less restrictive than those \
contained herein.

<strong>3. TERM AND TERMINATION</strong>

This Agreement shall remain in effect for a period of two (2) years from the Effective Date, unless \
earlier terminated by either Party upon thirty (30) days' prior written notice to the other Party. \
The obligations of confidentiality set forth in Section 2 shall survive the termination or expiration \
of this Agreement for a period of three (3) years following such termination or expiration.

<strong>4. RETURN OF MATERIALS</strong>

Upon termination of this Agreement or upon request of the Disclosing Party, the Receiving Party \
shall promptly return or destroy all tangible materials containing Confidential Information and \
shall certify in writing that it has done so. Notwithstanding the foregoing, the Receiving Party \
may retain one (1) archival copy of the Confidential Information solely for the purpose of \
monitoring its ongoing obligations under this Agreement.

<strong>5. NO LICENSE OR WARRANTY</strong>

Nothing in this Agreement shall be construed as granting any rights, by license or otherwise, to \
any Confidential Information, except as expressly set forth herein. ALL CONFIDENTIAL INFORMATION IS \
PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.

<strong>6. REMEDIES</strong>

Each Party acknowledges that any breach of this Agreement may cause <em>irreparable harm</em> to the \
Disclosing Party for which monetary damages alone would not be an adequate remedy. Accordingly, the \
Disclosing Party shall be entitled to seek equitable relief, including injunction and specific \
performance, in addition to all other remedies available at law or in equity.

<strong>7. GOVERNING LAW</strong>

This Agreement shall be governed by and construed in accordance with the laws of the State of \
Delaware, without regard to its conflict of laws principles. Any legal action or proceeding arising \
under this Agreement shall be brought <em>exclusively</em> in the federal or state courts located in \
Wilmington, Delaware, and the Parties hereby consent to personal jurisdiction and venue therein.

<strong>8. MISCELLANEOUS</strong>

This Agreement constitutes the entire agreement between the Parties with respect to the subject \
matter hereof and supersedes all prior and contemporaneous agreements, understandings, negotiations, \
and discussions. This Agreement may not be amended except by a written instrument signed by both \
Parties. Neither Party may assign this Agreement without the prior written consent of the other \
Party. If any provision of this Agreement is found to be unenforceable, the remaining provisions \
shall continue in full force and effect.

IN WITNESS WHEREOF, the Parties have executed this Agreement as of the Effective Date.

ACME CORPORATION                        GLOBALTECH INDUSTRIES
By: _________________________           By: _________________________
Name: Sarah Mitchell                    Name: David Chen
Title: General Counsel                  Title: VP of Legal Affairs
Date: January 15, 2025                  Date: January 15, 2025
"""

LICENSE_CONTENT = """\
<strong>SOFTWARE LICENSE AGREEMENT</strong>

This Software License Agreement (the "<u>Agreement</u>") is entered into as of February 1, 2025 (the \
"<u>Effective Date</u>") by and between CloudFlow Inc., a Delaware corporation with offices at 450 \
Market Street, Suite 1200, San Francisco, CA 94105 ("Licensor"), and the entity agreeing to \
these terms ("Customer").

<strong>1. DEFINITIONS</strong>

1.1 "<u>CloudFlow Platform</u>" means the Licensor's proprietary cloud-based software-as-a-service \
platform for workflow automation, data integration, and business process management, including \
all updates, upgrades, and documentation provided by Licensor during the Subscription Term.

1.2 "<u>Authorized Users</u>" means individuals who are employees or contractors of Customer and who \
have been granted access credentials to use the CloudFlow Platform. The maximum number of \
Authorized Users is specified in the applicable Order Form.

1.3 "<u>Order Form</u>" means the ordering document executed by the Parties that specifies the \
subscription tier, number of Authorized Users, fees, and Subscription Term.

1.4 "<u>Subscription Term</u>" means the period during which Customer has the right to access and use \
the CloudFlow Platform, as specified in the Order Form.

<strong>2. LICENSE GRANT AND RESTRICTIONS</strong>

2.1 License Grant. Subject to the terms and conditions of this Agreement and payment of all \
applicable fees, Licensor hereby grants Customer a <em>non-exclusive, non-transferable, non-sublicensable</em> \
right to access and use the CloudFlow Platform during the Subscription Term solely for Customer's \
internal business operations and within the usage limits specified in the Order Form.

2.2 Usage Limits. Customer <em>shall not</em> exceed the number of Authorized Users or the data storage \
and API call limits specified in the Order Form. If Customer exceeds such limits, Licensor may \
charge overage fees at the rates specified in the Order Form or, upon thirty (30) days' notice, \
suspend access until Customer's usage conforms to the applicable limits.

2.3 Restrictions. Customer <em>shall not</em>: (a) sublicense, sell, resell, transfer, assign, or distribute \
the CloudFlow Platform; (b) modify or make derivative works based upon the CloudFlow Platform; \
(c) reverse engineer or access the CloudFlow Platform in order to build a competitive product or \
service; (d) use the CloudFlow Platform to store or transmit any material that infringes the \
intellectual property rights of any third party or that is unlawful, defamatory, or otherwise \
objectionable; or (e) use the CloudFlow Platform to transmit malicious code.

<strong>3. INTELLECTUAL PROPERTY</strong>

3.1 Licensor IP. As between the Parties, Licensor <em>exclusively</em> owns all right, title, and interest \
in and to the CloudFlow Platform, including all related intellectual property rights. No rights are \
granted to Customer hereunder other than as expressly set forth in this Agreement.

3.2 Customer Data. As between the Parties, Customer exclusively owns all right, title, and interest \
in and to all data, content, and information submitted by Customer or its Authorized Users to the \
CloudFlow Platform ("<u>Customer Data</u>"). Customer grants Licensor a non-exclusive, worldwide license to \
host, copy, transmit, and display Customer Data solely as necessary to provide the CloudFlow Platform \
in accordance with this Agreement.

3.3 Feedback. If Customer provides any suggestions, enhancement requests, or other feedback regarding \
the CloudFlow Platform ("<u>Feedback</u>"), Licensor shall have the right to use such Feedback without \
restriction or compensation to Customer.

<strong>4. FEES AND PAYMENT</strong>

4.1 Fees. Customer shall pay the fees specified in the Order Form. All fees are quoted in U.S. \
dollars, are non-refundable, and are due within thirty (30) days of the invoice date. Late payments \
shall accrue interest at the rate of 1.5% per month or the maximum rate permitted by law, whichever \
is less.

4.2 Taxes. All fees are exclusive of taxes. Customer shall be responsible for all sales, use, and \
similar taxes arising from Customer's purchase under this Agreement, excluding taxes based on \
Licensor's income.

<strong>5. WARRANTIES AND DISCLAIMERS</strong>

5.1 Licensor Warranty. Licensor warrants that during the Subscription Term the CloudFlow Platform \
will perform materially in accordance with its published documentation. Licensor's <em>sole obligation</em> \
and Customer's <em>exclusive remedy</em> for a breach of this warranty shall be, at Licensor's option, to \
either (a) correct the non-conforming functionality or (b) refund a pro-rata portion of the prepaid \
fees for the affected period.

5.2 Disclaimer. EXCEPT AS EXPRESSLY SET FORTH IN SECTION 5.1, THE CLOUDFLOW PLATFORM IS PROVIDED \
"AS IS." LICENSOR HEREBY <em>DISCLAIMS ALL WARRANTIES</em>, WHETHER EXPRESS, IMPLIED, STATUTORY, OR \
OTHERWISE, INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, \
TITLE, AND NON-INFRINGEMENT.

<strong>6. LIMITATION OF LIABILITY</strong>

6.1 Liability Cap. IN NO EVENT SHALL EITHER PARTY'S AGGREGATE LIABILITY ARISING OUT OF OR RELATED \
TO THIS AGREEMENT EXCEED THE TOTAL FEES PAID BY CUSTOMER TO LICENSOR IN THE PRECEDING TWELVE (12) \
MONTHS UNDER THE APPLICABLE ORDER FORM. THE FOREGOING LIMITATION SHALL APPLY WHETHER AN ACTION IS \
IN CONTRACT OR TORT AND REGARDLESS OF THE THEORY OF LIABILITY.

6.2 Exclusion of Consequential Damages. IN NO EVENT SHALL EITHER PARTY BE LIABLE FOR ANY INDIRECT, \
INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, OR ANY LOSS OF PROFITS, REVENUE, DATA, \
OR BUSINESS OPPORTUNITIES ARISING OUT OF OR RELATED TO THIS AGREEMENT, EVEN IF SUCH PARTY HAS \
BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

<strong>7. TERM AND TERMINATION</strong>

7.1 Term. This Agreement commences on the Effective Date and continues for the Subscription Term \
specified in the Order Form, unless earlier terminated in accordance with this Section 7.

7.2 Termination for Cause. Either Party may terminate this Agreement upon written notice if the \
other Party materially breaches this Agreement and fails to cure such breach within thirty (30) \
days of receiving written notice thereof.

7.3 Effect of Termination. Upon termination or expiration of this Agreement: (a) Customer's right \
to access and use the CloudFlow Platform shall <em>immediately cease</em>; (b) Licensor shall make Customer \
Data available for export for a period of thirty (30) days following termination; and (c) each \
Party shall return or destroy all Confidential Information of the other Party.

<strong>8. GENERAL PROVISIONS</strong>

8.1 Governing Law. This Agreement shall be governed by the laws of the State of California, without \
regard to its conflict of laws provisions.

8.2 Entire Agreement. This Agreement, together with all Order Forms, constitutes the entire \
agreement between the Parties with respect to the subject matter hereof.

8.3 Assignment. Neither Party may assign this Agreement without the prior written consent of the \
other Party, except in connection with a merger, acquisition, or sale of all or substantially all \
of its assets.

8.4 Notices. All notices under this Agreement shall be in writing and shall be deemed given when \
delivered personally, sent by confirmed email, or sent by certified mail, return receipt requested, \
to the addresses specified in the Order Form.

IN WITNESS WHEREOF, the Parties have executed this Agreement as of the Effective Date.

CLOUDFLOW INC.                          CUSTOMER
By: _________________________           By: _________________________
Name: Jennifer Park                     Name: _________________________
Title: Chief Executive Officer          Title: _________________________
Date: February 1, 2025                  Date: _________________________
"""

EMPLOYMENT_CONTENT = """\
<strong>EMPLOYMENT AGREEMENT</strong>

This Employment Agreement (the "<u>Agreement</u>") is entered into as of March 1, 2025 (the "<u>Effective Date</u>") \
by and between Meridian Labs Inc., a Delaware corporation with its principal place of business at \
800 Gateway Boulevard, South San Francisco, CA 94080 ("Company"), and Alex Rivera ("Employee").

<strong>RECITALS</strong>

WHEREAS, the Company desires to employ Employee, and Employee desires to accept such employment, \
subject to the terms and conditions set forth herein;

NOW, THEREFORE, in consideration of the mutual covenants and agreements contained herein, and for \
other good and valuable consideration, the receipt and sufficiency of which are hereby acknowledged, \
the Parties agree as follows:

<strong>1. POSITION AND DUTIES</strong>

1.1 Position. The Company hereby employs Employee as Senior Software Engineer, reporting to the \
Vice President of Engineering. Employee shall perform such duties and responsibilities as are \
customarily associated with such position and as may be reasonably assigned by the Company from \
time to time.

1.2 Full-Time Employment. Employee shall devote substantially all of Employee's business time, \
attention, and energies to the performance of Employee's duties hereunder. Employee may engage in \
civic, charitable, or passive investment activities, provided that such activities do not interfere \
with Employee's obligations under this Agreement.

1.3 At-Will Employment. Employee's employment with the Company is <em>at-will</em>, meaning that either \
the Company or Employee may terminate the employment relationship at any time, with or without \
cause, and with or without notice, subject to the provisions of Section 6 below.

<strong>2. COMPENSATION</strong>

2.1 Base Salary. The Company shall pay Employee an annual base salary of One Hundred Eighty-Five \
Thousand Dollars ($185,000) (the "<u>Base Salary</u>"), payable in accordance with the Company's standard \
payroll practices and subject to applicable withholdings and deductions. The Base Salary shall be \
reviewed annually by the Company and may be adjusted at the Company's sole discretion.

2.2 Annual Bonus. Employee shall be eligible to participate in the Company's annual bonus program, \
with a target bonus of fifteen percent (15%) of the Base Salary, subject to the achievement of \
individual and company performance objectives as determined by the Company. Bonus payments, if any, \
shall be made within ninety (90) days following the end of the applicable fiscal year.

2.3 Equity Compensation. Subject to approval by the Company's Board of Directors, Employee shall \
be granted an option to purchase Fifteen Thousand (15,000) shares of the Company's common stock \
(the "<u>Stock Option</u>") under the Company's 2024 Equity Incentive Plan (the "<u>Plan</u>"). The Stock Option \
shall have an exercise price equal to the fair market value of the Company's common stock on the \
date of grant. The Stock Option shall vest over a four (4) year period, with twenty-five percent \
(25%) vesting on the first anniversary of the Effective Date and the remainder vesting in equal \
monthly installments over the subsequent thirty-six (36) months, subject to Employee's continued \
employment with the Company. The Stock Option shall be subject to the terms and conditions of the \
Plan and the applicable stock option agreement.

<strong>3. BENEFITS</strong>

3.1 Health Insurance. Employee shall be eligible to participate in the Company's group health \
insurance plans, including medical, dental, and vision coverage, subject to the terms and conditions \
of such plans and the Company's benefits policies.

3.2 Paid Time Off. Employee shall be entitled to twenty (20) days of paid time off per calendar \
year, which accrues on a semi-monthly basis. Unused paid time off may be carried over to the \
following year, subject to a maximum accrual cap of thirty (30) days.

3.3 Other Benefits. Employee shall be eligible to participate in all other benefit programs \
generally made available to similarly situated employees of the Company, including the Company's \
401(k) plan (with a Company match of up to four percent (4%) of eligible compensation), life \
insurance, and disability insurance, in each case subject to the terms of the applicable plan \
documents.

<strong>4. CONFIDENTIALITY</strong>

4.1 Confidential Information. Employee acknowledges that during the course of employment, Employee \
will have access to and become acquainted with Confidential Information. "<u>Confidential Information</u>" \
includes, but is not limited to, trade secrets, proprietary data, source code, algorithms, customer \
lists, business strategies, financial information, product roadmaps, and any other information that \
derives independent economic value from not being generally known.

4.2 Non-Disclosure. Employee agrees that during and after employment with the Company, Employee \
<em>shall not</em>, directly or indirectly, use, disclose, or make available to any third party any \
Confidential Information, except as required in the performance of Employee's duties or as \
authorized in writing by the Company. This obligation shall survive the termination of this \
Agreement <em>indefinitely</em> with respect to trade secrets and for a period of three (3) years with \
respect to other Confidential Information.

4.3 Inventions Assignment. Employee agrees to promptly disclose and hereby assigns to the Company \
all inventions, developments, discoveries, and works of authorship, whether or not patentable, \
that Employee conceives, develops, or reduces to practice during the term of employment and that \
relate to the Company's business or result from the use of the Company's resources. This provision \
is subject to the limitations of California Labor Code Section 2870.

<strong>5. NON-COMPETE AND NON-SOLICITATION</strong>

5.1 Non-Compete. During Employee's employment and for a period of twelve (12) months following the \
termination of employment for any reason (the "<u>Restricted Period</u>"), Employee <em>shall not</em>, directly or \
indirectly, engage in, own, manage, operate, consult for, or be employed by any business that \
competes with the Company's business within the geographic markets in which the Company operates. \
The Parties acknowledge that this restriction is reasonable in scope and duration and is necessary \
to protect the Company's legitimate business interests. Notwithstanding the foregoing, this \
Section 5.1 shall be enforceable only to the extent permitted by applicable law.

5.2 Non-Solicitation. During the Restricted Period, Employee <em>shall not</em>, directly or indirectly: \
(a) solicit, recruit, or hire any employee or contractor of the Company; or (b) solicit or attempt \
to divert any customer, client, or business partner of the Company.

<strong>6. TERMINATION</strong>

6.1 Termination Without Cause. The Company may terminate Employee's employment without <u>Cause</u> at \
any time upon thirty (30) days' prior written notice. In the event of termination without Cause, \
the Company shall provide Employee with: (a) continued payment of the Base Salary for a period of \
three (3) months following the termination date (the "<u>Severance Period</u>"); and (b) Company-paid \
COBRA continuation coverage during the Severance Period, subject to Employee's execution of a \
general release of claims in a form satisfactory to the Company.

6.2 Termination for Cause. The Company may terminate Employee's employment for Cause <em>immediately</em> \
upon written notice. "Cause" means: (a) Employee's material breach of this Agreement; (b) Employee's \
conviction of, or plea of guilty or nolo contendere to, a felony; (c) Employee's gross negligence \
or willful misconduct in the performance of duties; or (d) Employee's continued failure to perform \
assigned duties after receiving written notice and a reasonable opportunity to cure.

6.3 Resignation. Employee may resign at any time upon thirty (30) days' prior written notice to \
the Company. The Company, in its sole discretion, may waive some or all of the notice period.

6.4 Effect of Termination. Upon any termination of employment, Employee shall: (a) return all \
Company property, including equipment, documents, and data; (b) cooperate with the Company in \
transitioning Employee's duties and responsibilities; and (c) comply with the surviving obligations \
under Sections 4 and 5 of this Agreement.

<strong>7. GENERAL PROVISIONS</strong>

7.1 Governing Law. This Agreement shall be governed by and construed in accordance with the laws \
of the State of California, without regard to its conflict of laws principles.

7.2 Entire Agreement. This Agreement constitutes the entire agreement between the Parties with \
respect to the subject matter hereof and supersedes all prior agreements, representations, and \
understandings, whether written or oral.

7.3 Amendments. This Agreement may not be amended or modified except by a written instrument signed \
by both Parties.

7.4 Severability. If any provision of this Agreement is held to be invalid or unenforceable, the \
remaining provisions shall continue in full force and effect.

7.5 Counterparts. This Agreement may be executed in counterparts, each of which shall be deemed an \
original, and all of which together shall constitute one and the same instrument.

IN WITNESS WHEREOF, the Parties have executed this Agreement as of the Effective Date.

MERIDIAN LABS INC.                      EMPLOYEE
By: _________________________           _________________________
Name: Dr. Lisa Nakamura                 Alex Rivera
Title: Chief Executive Officer
Date: March 1, 2025                     Date: March 1, 2025
"""

# ---------------------------------------------------------------------------
# Change history entries
# ---------------------------------------------------------------------------

NDA_CHANGE_1 = {
    "changes": [
        {
            "operation": "replace",
            "target": {"text": "the laws of the State of California", "occurrence": 1},
            "replacement": "the laws of the State of Delaware",
        }
    ],
    "summary": "Changed governing law from California to Delaware",
}

NDA_CHANGE_2 = {
    "changes": [
        {
            "operation": "replace",
            "target": {"text": "one (1) year", "occurrence": 1},
            "replacement": "two (2) years",
        }
    ],
    "summary": "Extended agreement term from one (1) year to two (2) years",
}

LICENSE_CHANGE_1 = {
    "changes": [
        {
            "operation": "replace",
            "target": {"text": "$10,000", "occurrence": 1},
            "replacement": "THE TOTAL FEES PAID BY CUSTOMER TO LICENSOR IN THE PRECEDING TWELVE (12) MONTHS UNDER THE APPLICABLE ORDER FORM",
        }
    ],
    "summary": "Changed liability cap from fixed $10,000 to total fees paid in the preceding twelve months",
}

EMPLOYMENT_CHANGE_1 = {
    "changes": [
        {
            "operation": "replace",
            "target": {"text": "twenty-four (24) months", "occurrence": 1},
            "replacement": "twelve (12) months",
        }
    ],
    "summary": "Reduced non-compete period from 24 months to 12 months",
}

EMPLOYMENT_CHANGE_2 = {
    "changes": [
        {
            "operation": "replace",
            "target": {"text": "One Hundred Seventy-Five Thousand Dollars ($175,000)", "occurrence": 1},
            "replacement": "One Hundred Eighty-Five Thousand Dollars ($185,000)",
        }
    ],
    "summary": "Increased base salary from $175,000 to $185,000",
}

# ---------------------------------------------------------------------------
# Suggestion seed data (on the NDA document)
# ---------------------------------------------------------------------------

NDA_SUGGESTION_1 = {
    "original_text": "thirty (30) days",
    "replacement_text": "fifteen (15) business days",
    "position": 3397,
    "status": "pending",
    "author": "guest3847",
}

NDA_SUGGESTION_2 = {
    "original_text": "GlobalTech Industries,",
    "replacement_text": "GlobalTech Industries and its affiliates,",
    "position": 299,
    "status": "pending",
    "author": "guest1592",
}

NDA_SUGGESTION_3 = {
    "original_text": "monetary damages would be an inadequate remedy",
    "replacement_text": "monetary damages alone would not be an adequate remedy",
    "position": 4537,
    "status": "accepted",
    "author": "guest3847",
}

NDA_SUGGESTION_3_COMMENTS = [
    {
        "author": "guest3847",
        "content": "The original phrasing may be too weak to support an injunction motion. Suggesting we strengthen this language.",
    },
    {
        "author": "guest1592",
        "content": "Agreed. 'Would not be an adequate remedy' is more consistent with the standard courts apply when granting equitable relief.",
    },
    {
        "author": "guest1592",
        "content": "Accepted. Updated to reflect the stronger formulation.",
    },
]


def seed_database(database_url: str | None = None) -> None:
    """Seed the database with sample legal documents if empty."""
    url = database_url or settings.database_url
    with psycopg.connect(url, row_factory=dict_row) as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM documents").fetchone()
        if row["cnt"] > 0:
            return

        now = "2025-01-15T10:00:00"

        # --- Document 1: NDA (2 changes -> version 3, then frozen) ---
        nda_id = str(uuid4())
        conn.execute(
            "INSERT INTO documents (id, title, content, version, created_at, updated_at, frozen_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (nda_id, "Mutual Non-Disclosure Agreement - Acme Corp / GlobalTech Industries",
             NDA_CONTENT, 4, now, "2025-01-18T11:00:00", "2025-01-18T09:00:00"),
        )

        nda_hist_1_id = str(uuid4())
        conn.execute(
            "INSERT INTO change_history (id, document_id, version, changes_json, summary, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (nda_hist_1_id, nda_id, 2, json.dumps(NDA_CHANGE_1["changes"]),
             NDA_CHANGE_1["summary"], "2025-01-16T09:15:00"),
        )

        nda_hist_2_id = str(uuid4())
        conn.execute(
            "INSERT INTO change_history (id, document_id, version, changes_json, summary, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (nda_hist_2_id, nda_id, 3, json.dumps(NDA_CHANGE_2["changes"]),
             NDA_CHANGE_2["summary"], "2025-01-17T14:30:00"),
        )

        # --- Document 2: Software License Agreement ---
        license_id = str(uuid4())
        conn.execute(
            "INSERT INTO documents (id, title, content, version, created_at, updated_at, frozen_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (license_id, "Software License Agreement - CloudFlow Platform",
             LICENSE_CONTENT, 2, "2025-02-01T10:00:00", "2025-02-05T16:45:00", None),
        )

        license_hist_1_id = str(uuid4())
        conn.execute(
            "INSERT INTO change_history (id, document_id, version, changes_json, summary, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (license_hist_1_id, license_id, 2, json.dumps(LICENSE_CHANGE_1["changes"]),
             LICENSE_CHANGE_1["summary"], "2025-02-05T16:45:00"),
        )

        # --- Document 3: Employment Agreement ---
        employment_id = str(uuid4())
        conn.execute(
            "INSERT INTO documents (id, title, content, version, created_at, updated_at, frozen_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (employment_id, "Employment Agreement - Senior Software Engineer, Meridian Labs Inc.",
             EMPLOYMENT_CONTENT, 3, "2025-03-01T10:00:00", "2025-03-04T11:20:00", None),
        )

        employment_hist_1_id = str(uuid4())
        conn.execute(
            "INSERT INTO change_history (id, document_id, version, changes_json, summary, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (employment_hist_1_id, employment_id, 2, json.dumps(EMPLOYMENT_CHANGE_1["changes"]),
             EMPLOYMENT_CHANGE_1["summary"], "2025-03-03T09:00:00"),
        )

        employment_hist_2_id = str(uuid4())
        conn.execute(
            "INSERT INTO change_history (id, document_id, version, changes_json, summary, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (employment_hist_2_id, employment_id, 3, json.dumps(EMPLOYMENT_CHANGE_2["changes"]),
             EMPLOYMENT_CHANGE_2["summary"], "2025-03-04T11:20:00"),
        )

        # --- History entry for accepted suggestion ---
        nda_hist_3_id = str(uuid4())
        conn.execute(
            "INSERT INTO change_history (id, document_id, version, changes_json, summary, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (nda_hist_3_id, nda_id, 4,
             json.dumps([{
                 "operation": "replace",
                 "target": {"text": NDA_SUGGESTION_3["original_text"], "occurrence": 1},
                 "replacement": NDA_SUGGESTION_3["replacement_text"],
             }]),
             f"Accepted suggestion by {NDA_SUGGESTION_3['author']} (approved by guest1592): "
             f"Replaced '{NDA_SUGGESTION_3['original_text'][:40]}' with '{NDA_SUGGESTION_3['replacement_text'][:40]}'",
             "2025-01-18T11:00:00"),
        )

        # --- Suggestions on the NDA document ---
        suggestion_1_id = str(uuid4())
        conn.execute(
            "INSERT INTO suggestions (id, document_id, original_text, replacement_text, position, author, status, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (suggestion_1_id, nda_id, NDA_SUGGESTION_1["original_text"],
             NDA_SUGGESTION_1["replacement_text"], NDA_SUGGESTION_1["position"],
             NDA_SUGGESTION_1["author"], "pending", "2025-01-18T09:30:00"),
        )

        suggestion_2_id = str(uuid4())
        conn.execute(
            "INSERT INTO suggestions (id, document_id, original_text, replacement_text, position, author, status, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (suggestion_2_id, nda_id, NDA_SUGGESTION_2["original_text"],
             NDA_SUGGESTION_2["replacement_text"], NDA_SUGGESTION_2["position"],
             NDA_SUGGESTION_2["author"], "pending", "2025-01-18T10:30:00"),
        )

        suggestion_3_id = str(uuid4())
        conn.execute(
            "INSERT INTO suggestions (id, document_id, original_text, replacement_text, position, author, status, created_at, resolved_at, resolved_by) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (suggestion_3_id, nda_id, NDA_SUGGESTION_3["original_text"],
             NDA_SUGGESTION_3["replacement_text"], NDA_SUGGESTION_3["position"],
             NDA_SUGGESTION_3["author"], "accepted", "2025-01-18T09:15:00",
             "2025-01-18T11:00:00", "guest1592"),
        )

        # Comment thread on the accepted suggestion
        for i, comment in enumerate(NDA_SUGGESTION_3_COMMENTS):
            comment_id = str(uuid4())
            conn.execute(
                "INSERT INTO suggestion_comments (id, suggestion_id, author, content, created_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (comment_id, suggestion_3_id, comment["author"],
                 comment["content"], f"2025-01-18T{11 + i}:00:00"),
            )

        conn.commit()
        logger.info("Seeded database with 3 sample documents")

        # --- Load pre-computed embeddings (no API key needed) ---
        _seed_embeddings(conn)


def _seed_embeddings(conn: psycopg.Connection) -> None:
    """Load pre-computed embeddings from JSON and insert into the database.

    Embeddings are keyed by document title so they survive UUID regeneration
    across fresh seeds. Requires pgvector to be registered on the connection.
    """
    if not _EMBEDDINGS_PATH.exists():
        logger.info("No seed_embeddings.json found, skipping embedding seed")
        return

    with open(_EMBEDDINGS_PATH) as f:
        embeddings_by_title = json.load(f)

    docs = conn.execute("SELECT id, title FROM documents").fetchall()
    seeded = 0

    for doc in docs:
        doc_id = doc["id"]
        title = doc["title"]
        if title not in embeddings_by_title:
            continue

        data = embeddings_by_title[title]

        # Document-level embedding
        conn.execute(
            "UPDATE documents SET embedding = %s::vector WHERE id = %s",
            (str(data["embedding"]), doc_id),
        )

        # Chunk-level embeddings
        for idx, chunk in enumerate(data.get("chunks", [])):
            conn.execute(
                "INSERT INTO chunk_embeddings (document_id, chunk_index, chunk_text, position, embedding, model) "
                "VALUES (%s, %s, %s, %s, %s::vector, %s)",
                (doc_id, idx, chunk["text"], chunk["position"],
                 str(chunk["embedding"]), settings.embedding_model),
            )

        seeded += 1

    conn.commit()
    logger.info("Seeded embeddings for %d documents", seeded)

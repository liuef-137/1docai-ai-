"""Few-shot training examples for English contract risk analysis.

These examples are injected as user/assistant message pairs before the actual
contract to be analyzed, helping the LLM produce structured, jurisdiction-aware
risk assessments for English-language agreements.
"""

ENGLISH_SERVICE_AGREEMENT_EXAMPLE = {
    "text": """SERVICE AGREEMENT

This Service Agreement ("Agreement") is entered into as of January 1, 2024, by and between ABC Tech, Inc. ("Provider") and XYZ Corp ("Client").

1. Services. Provider shall perform software development services as described in Exhibit A.
2. Payment. Client shall pay all fees within sixty (60) days of invoice. Late payments subject to 1.5% monthly service charge.
3. Limitation of Liability. Provider's total liability shall not exceed the total amount paid by Client under this Agreement in the twelve (12) months preceding the claim.
4. Termination. Either party may terminate this Agreement for convenience with thirty (30) days written notice.
5. Governing Law. This Agreement shall be governed by the laws of the State of Delaware.
""",
    "expected": {
        "contract_type": "service",
        "score": 68,
        "risk_level": "medium",
        "one_line_summary": "Payment terms and liability cap create moderate risk for the service provider.",
        "risk_items": [
            {
                "clause_name": "Payment Terms",
                "clause_location": "Section 2",
                "risk_level": "medium",
                "description": "Sixty-day payment period and 1.5% monthly late fee may strain Provider cash flow and may be unenforceable in some jurisdictions.",
                "plain_explanation": "Client has two months to pay, and late fees could be too high to be legal.",
                "suggestion": "Reduce payment term to net 30 and cap late fee at the maximum lawful rate (often 1% per month).",
                "legal_basis": "UCC Article 2 / state usury and contract law"
            },
            {
                "clause_name": "Limitation of Liability",
                "clause_location": "Section 3",
                "risk_level": "medium",
                "description": "Liability cap based on 12-month fees may be insufficient for breaches involving data loss or IP infringement.",
                "plain_explanation": "If something big goes wrong, the most you can recover is one year of fees.",
                "suggestion": "Carve out liability for gross negligence, willful misconduct, data breaches, and IP indemnification from the cap.",
                "legal_basis": "Common law; enforceability varies by jurisdiction"
            },
            {
                "clause_name": "Termination for Convenience",
                "clause_location": "Section 4",
                "risk_level": "low",
                "description": "Either party may terminate with 30 days notice, creating project continuity risk but is standard for service agreements.",
                "plain_explanation": "Either side can walk away with one month's notice.",
                "suggestion": "Add wind-down obligations, data return provisions, and payment for work performed up to termination.",
                "legal_basis": "Common law contract principles"
            }
        ],
        "suggestions": [
            "Clarify deliverables and acceptance criteria in Exhibit A.",
            "Add confidentiality and IP ownership clauses.",
            "Include a dispute resolution mechanism such as mediation or arbitration."
        ],
        "key_obligations": [
            {"party": "Provider", "obligation": "Perform software development services per Exhibit A"},
            {"party": "Client", "obligation": "Pay fees within 60 days of invoice"}
        ]
    }
}

ENGLISH_EMPLOYMENT_AGREEMENT_EXAMPLE = {
    "text": """EMPLOYMENT AGREEMENT

This Employment Agreement ("Agreement") is made as of March 1, 2024, by and between Acme Corp ("Employer") and John Doe ("Employee").

1. Position. Employee is hired as Senior Software Engineer.
2. Compensation. Employer shall pay an annual salary of $120,000, payable semi-monthly.
3. Non-Compete. Employee shall not engage in any competing business within 50 miles for two (2) years after termination.
4. Confidentiality. Employee agrees to keep all Employer information confidential indefinitely.
5. Dispute Resolution. Any dispute shall be resolved through binding arbitration in New York, NY.
""",
    "expected": {
        "contract_type": "labor",
        "score": 55,
        "risk_level": "medium",
        "one_line_summary": "Overly broad non-compete and indefinite confidentiality terms create enforceability risk for the employee.",
        "risk_items": [
            {
                "clause_name": "Non-Compete Clause",
                "clause_location": "Section 3",
                "risk_level": "high",
                "description": "A 50-mile, two-year non-compete without geographic or role limitation and no mention of consideration may be unenforceable in many states.",
                "plain_explanation": "You can't work for a competitor within 50 miles for two years, which may not hold up in court.",
                "suggestion": "Limit non-compete to 6-12 months, narrow geographic scope to direct markets, and ensure separate consideration where required by state law.",
                "legal_basis": "State-specific non-compete statutes and common law"
            },
            {
                "clause_name": "Confidentiality Period",
                "clause_location": "Section 4",
                "risk_level": "medium",
                "description": "Indefinite confidentiality obligation may conflict with rules that trade-secret protection lasts only as long as information remains a secret.",
                "plain_explanation": "You're asked to keep secrets forever, which may be too broad.",
                "suggestion": "Define confidentiality period (e.g., during employment plus 3-5 years) and carve out publicly available information.",
                "legal_basis": "Uniform Trade Secrets Act (UTSA) / state trade secret law"
            },
            {
                "clause_name": "Arbitration Clause",
                "clause_location": "Section 5",
                "risk_level": "low",
                "description": "Mandatory arbitration in New York may limit Employee's ability to pursue class actions or seek public injunctive relief.",
                "plain_explanation": "Disputes go to private arbitration, not court.",
                "suggestion": "Ensure arbitration clause is mutual, covers costs for prevailing party, and preserves rights to seek injunctive relief in court.",
                "legal_basis": "Federal Arbitration Act (FAA)"
            }
        ],
        "suggestions": [
            "Add explicit consideration for restrictive covenants where required.",
            "Include a severability clause for unenforceable provisions.",
            "Clarify whether the agreement is at-will or for a fixed term."
        ],
        "key_obligations": [
            {"party": "Employer", "obligation": "Pay annual salary of $120,000"},
            {"party": "Employee", "obligation": "Perform duties as Senior Software Engineer and maintain confidentiality"}
        ]
    }
}

ENGLISH_NDA_EXAMPLE = {
    "text": """MUTUAL NON-DISCLOSURE AGREEMENT

This NDA ("Agreement") is entered into as of April 15, 2024 ("Effective Date") by and between Innovate LLC ("Discloser") and Venture Partners Inc ("Recipient").

1. Definition of Confidential Information. All non-public, proprietary, or confidential information disclosed by Discloser.
2. Obligations of Recipient. Recipient shall hold all Confidential Information in strict confidence and not disclose to any third parties.
3. Term. This Agreement shall remain in effect for five (5) years from the Effective Date.
4. Return of Information. Upon termination, Recipient shall return all Confidential Information within ten (10) business days.
5. Governing Law. This Agreement is governed by the laws of California.
""",
    "expected": {
        "contract_type": "nda",
        "score": 72,
        "risk_level": "low",
        "one_line_summary": "Standard mutual NDA with reasonable term and return obligations, but missing injunctive relief and residual-memory carve-outs.",
        "risk_items": [
            {
                "clause_name": "Definition of Confidential Information",
                "clause_location": "Section 1",
                "risk_level": "low",
                "description": "Broad definition may capture information that is not actually confidential; best practice is to mark or identify confidential disclosures.",
                "plain_explanation": "The definition of secrets is very broad.",
                "suggestion": "Require written marking or oral confirmation within a short period to reduce ambiguity.",
                "legal_basis": "Uniform Trade Secrets Act (UTSA)"
            },
            {
                "clause_name": "Injunctive Relief",
                "clause_location": "Not present",
                "risk_level": "medium",
                "description": "Agreement does not explicitly preserve the right to seek injunctive relief for actual or threatened disclosure.",
                "plain_explanation": "If secrets are about to leak, there's no clear right to ask a court to stop it quickly.",
                "suggestion": "Add a clause acknowledging that breach may cause irreparable harm and entitles Discloser to seek injunctive relief.",
                "legal_basis": "Common law equity principles"
            }
        ],
        "suggestions": [
            "Add standard exclusions for publicly available and independently developed information.",
            "Include a residual-memory clause if appropriate for the jurisdiction.",
            "Specify permitted recipients such as employees and advisors on a need-to-know basis."
        ],
        "key_obligations": [
            {"party": "Recipient", "obligation": "Hold Confidential Information in strict confidence and not disclose to third parties"},
            {"party": "Recipient", "obligation": "Return all Confidential Information within 10 business days of termination"}
        ]
    }
}

ENGLISH_EXAMPLES = [
    ENGLISH_SERVICE_AGREEMENT_EXAMPLE,
    ENGLISH_EMPLOYMENT_AGREEMENT_EXAMPLE,
    ENGLISH_NDA_EXAMPLE,
]

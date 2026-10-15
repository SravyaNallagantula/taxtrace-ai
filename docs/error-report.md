# Error report

Client CL-20417, Okafor–Lindqvist, tax year 2025. The current engine return is v3, computed 2026-06-23. These notes do not change v3. Dollar effects use the packet's v3 rates or a named what-if result. They are not a new return, and they are not added together.

## Confirmed, and missed by the engine

1. **RSU basis is $0.** D11 states adjusted basis of $19,100, $19,100, and $9,420. Form 8949 reports basis $0 for lots N1, N3, and N4. The $38,200 of 2025 vest value is already on the Corvane W-2. Federal tax effect $15,535.56. California tax effect $2,444.80, applied to the $38,200 sold while the household was still a California resident. Partner sign-off is required. Finding `independent-rsu-basis`.

2. **1099-K is added on top of book income.** Schedule C gross receipts are $163,700, which is book income of $151,300 plus the Paywell 1099-K of $12,400. D15 says that $12,400 is already in sales. Federal tax effect $4,402. California tax effect $384.40. Partner sign-off is required. Finding `independent-1099k-double-count`.

3. **Federal estimate uses the questionnaire.** Form 1040 line 26 is $13,000. Three $3,000 payments are on the EFTPS sheet. Questionnaire qa-41 says $4,000. The IRS transcript shows a January 15 payment of $3,000. This changes the balance due, not the tax, so the stored tax effect is zero.

4. **A California estimate is designated 2024.** Form 540NR line 72 is $14,000 and includes the September 15 payment of $3,500 whose year field is 2024. The FTB holds that payment as a 2024 credit. The stored tax effect is zero. The 2025 California refund is overstated by the $3,500 payment.

5. **Vehicle donation uses $6,000.** Form 8283 takes the questionnaire amount. Form 1098-C says the charity sold the Subaru and box 4c gross proceeds are $2,900. The deduction is overstated by $3,100. Federal tax effect $806. California tax effect $148.80. A reviewer may sign.

6. **Self-employed health insurance.** Schedule 1 line 17 deducts $14,400 from the premium statement. Questionnaire qa-25 says both of Ngozi's employers offered family coverage, and that answer is not a source on the line. If the deduction is disallowed in full, the federal effect at the adjustment rate is $4,464 and the California effect is $604.80. That rate does not include a QBI change. Partner sign-off is required.

7. **Heat-pump replacement is inside repairs.** Schedule E includes the $11,000 Fremont Way invoice. The invoice is a full replacement with a permit. The packet's `hvac_improvement` alternative raises federal tax by $3,633 and California tax by $896. Those figures are copied from the packet. Partner sign-off is required.

8. **Spotify Family is inside software.** D15 includes $216 in software of $6,850, and Schedule C deducts the full account. The March 26 call says the charge is personal. Federal tax effect about $76.68. California tax effect about $6.70. A reviewer may sign.

9. **Theo's SSN does not match the card.** The organizer and document D71 differ. Federal e-file was rejected on 2026-07-13 with code R0000-504-02 and accepted the next day. v3 was computed before the card arrived. There is no fourth return version and no tax-dollar change. The raw numbers are not repeated here.

## Already flagged by the engine

Keep these diagnostics. They are not a second computation.

- Broker summary proceeds of $71,965 differ from the extracted lots by $250. D31 page 32 prints Ironwood REIT lot M18 with proceeds of $250.00. No extracted value exists for that lot.
- Questionnaire answers conflict with 282 brokerage sales and 12 digital-asset dispositions.
- Coinhaven lot C6 has no cost basis. A message estimates an amount paid in 2021. That message is not a document, so it is not booked.
- A handwritten receipt was read at confidence 0.41.
- Two contractor payments are at least $600 and Forms 1099-NEC were not filed. The engagement letter excludes those information returns.
- California AMT on the incentive stock option exercise was not computed. No California AMT figure is invented here.
- Form 8867 is not completed. The return claims the child tax credit and the credit for other dependents.

## Checked, and not treated as errors

Wages of $212,400 equal D08 box 1 of $104,600 plus D09 box 1 of $107,800. D10 repeats D09. The ESPP lot's broker basis of $3,825 plus the code B adjustment of $675 equals the D11 adjusted basis of $4,500. Mortgage interest of $21,847 matches the three Forms 1098. Business miles times the packet mileage rate of 0.70 equal the Schedule C deduction of $8,260, and those miles plus other miles equal the odometer change. Prior-year AGI of $228,409 matches the 2024 return.

## Open, and not booked

Schedule C deducts the full $3,480 of telephone and internet. The March 26 call estimates 70 percent business use of the mobile plan and 50 percent of internet. California wages on Schedule CA are $218,400 against federal wages of $212,400. D09 says the employer kept California as the work state through 2025-09-30, and the household's California residency ends 2025-07-14. No tax is computed for either item.

Fifty-one lines changed from 2024 by more than 10 percent and more than $1,000. Those are explanation flags under the firm's rule. They are not corrections.

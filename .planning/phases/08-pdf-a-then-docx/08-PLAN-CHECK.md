# Phase 8 plan review

2026-10-28: six sequential plans cover EXPO-06, EXPO-07 and EXPO-08.
All twelve SDK frontmatter/structure checks pass without warnings.

Independent `phase8_plan_check` initially found one blocker (DOCX review header
missing from CORS) and one warning (unspecified PDF/A reason transport). Revision
1 adds actual preflight/review/conversion checks and nine finite end-to-end reason
mappings. It also combines the authenticated Java validator with the existing
pinned native-tools CI image and removes unnecessary signed receipt machinery.
The acknowledgement binds source, complete output projection and policy digests.

Targeted independent recheck: **VERIFICATION PASSED**, no remaining issues.
The fixed twelve-positive floor, full successful-output validation, native
fidelity, warning-before-conversion and DOCX-removal proof remain mandatory.

This is static planning evidence. No converter, DOCX, hosted CI or product test
pass is implied. G3/G4/HEIC and no-deployment constraints remain unchanged.

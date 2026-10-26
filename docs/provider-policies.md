# Native provider policies

Use Configure → Read/write provider policies after adding integration-backed
provider devices to a logical vehicle. Preferred READ and WRITE providers are
independent. Each has a separate fallback switch; READ initially allows fallback,
WRITE initially does not. Every read field and supported command capability can
select an override. `__default__` means use the main preference. Legacy vehicles
retain their reviewed ordered read list until a policy is saved.

Fresh valid primary off/zero wins. Fallback reads never request a remote refresh
or wake a car. Missing explicitly preferred providers fail closed until reviewed.
Write fallback permits capability selection **before** dispatch only; it never
permits repeating an uncertain write through another integration. Policy selection
is not control authorization. All configured devices remain read-only.

Friendly names do not establish identity. Add Custom and Fleet devices to the same
logical vehicle only after verifying they represent that physical car; no VIN is
inferred from a name. One provider device cannot belong to two logical vehicles.
A charger device cannot be added as two logical controllers. Vehicles and chargers
are repeatable lists, not fixed pairs. Edit retains the logical UUID and policies.
Removal does not erase durable history. A deleted provider referenced by a policy
must be replaced or its preference explicitly reviewed before reads resume.

Optional household examples: ElLingo may select Custom for READ/WRITE; Blue Flux
may select Custom READ and Fleet WRITE. These are examples, never global defaults.

Exact Tesla registry VIN evidence (supported integration identifiers or Tesla
serial number) prevents assigning two device representations to different logical
vehicles. Conflicting known VINs cannot be linked into one logical vehicle; imported
conflicting/duplicate identities fail closed at runtime. Identifiers are compared
transiently, never exposed in diagnostics. Missing registry VIN evidence remains
unknown and requires manual verification; CM does not wake/fetch or infer from names.

# Compatibility Matrix

**Status:** DESIGN.

---

## 1. Android

| Minimum API | Requirement | Why |
|---|---|---|
| **API 23 (Android 6)** | `KeyGenParameterSpec`, `setUserAuthenticationRequired` | The minimum for hardware-backed keys with user authentication |
| **API 28 (Android 9)** | `setIsStrongBoxBacked`, `setInvalidatedByBiometricEnrollment` | StrongBox request and biometric invalidation |
| **API 31 (Android 12)** | `BiometricPrompt` with `setAllowedAuthenticators` | Device-credential fallback, explicit authenticator selection |

### Guarantee by tier

| Tier | API | Detection | Key extractable? | Present required? |
|---|---|---|---|---|
| **StrongBox** | 28+ | `getSecurityLevel() == SECURITY_LEVEL_STRONGBOX` | **No** | Yes |
| **TEE / TrustZone** | 23+ | `getSecurityLevel() == SECURITY_LEVEL_TRUSTED_ENVIRONMENT` and `isInsideSecureHardware()` | **No** (without root) | Yes |
| **Software-only** | 23+ | `getSecurityLevel() == SECURITY_LEVEL_SOFTWARE` | **Yes** | Yes |

**The low end is real.** A large share of Android devices in use have no
StrongBox, and a meaningful minority have no TEE. On a software-only
keystore the private key **can be extracted by an attacker with root or
a bootloader unlock**.

**Therefore the app must detect the tier and tell the user.** A user who
believes they have hardware-backed keys on a software-only device has a
false sense of security, and the platform's whole value rests on that
belief being correct.

---

## 2. iOS

| Minimum | Requirement | Why |
|---|---|---|
| **iOS 13** | `SecureEnclave` with `SecAccessControl` biometry flags | `biometryCurrentSet` needs it |
| **iOS 11** | `SecKeyCreateRandomKey` with `kSecAttrTokenIDSecureEnclave` | The baseline |

### Guarantee

| Tier | Available | Key extractable? | Present required? |
|---|---|---|---|
| **Secure Enclave** | iOS 13+ | **No — never, by construction** | Yes |
| **Fallback: device passcode** | Any supported iOS | **No** | Yes (passcode entry) |

**iOS has no software-only tier.** Every supported iOS device has a
Secure Enclave. This is a meaningful asymmetry with Android, and the
product should say so rather than pretending the platforms are
equivalent.

**Trade-off:** the passcode-only fallback is slower and less pleasant
than a biometric, but it is **not less secure** — it is still a
user-presence check.

---

## 3. Side by side

| | Android (TEE/StrongBox) | Android (software-only) | iOS |
|---|---|---|---|
| Key extractable | No | **Yes** | No |
| Biometric per operation | Yes | Yes | Yes |
| New enrolment invalidates | With `setInvalidatedByBiometricEnrollment` | Same | With `biometryCurrentSet` |
| Passcode fallback | Yes (`DEVICE_CREDENTIAL`) | Yes | Yes |
| **Usable as the trust anchor** | **Yes** | **With a disclosed caveat** | **Yes** |

---

## 4. What the PC needs to verify

The signature algorithm must be one both platforms can produce and the
PC can verify.

| Option | Availability | PC verification | Note |
|---|---|---|---|
| **Ed25519** | Android 33+ / iOS 13+ (via CryptoKit) | Needs a library or a pure-Python verifier | Cleanest curve, smallest keys |
| **ECDSA P-256** | **All** supported versions | Windows CNG is **unavailable** on this host (measured) | Needs a library too |

**The measurement that decides this:** the host has **no working OS
asymmetric signing provider**. CNG returns `NTE_NOT_SUPPORTED` for every
algorithm; the legacy CryptoAPI path fails with `NTE_BAD_KEYSET`. So the
PC must verify in software, which means either a maintained library
(breaking invariant C-1) or a reviewed pure-Python verifier.

**That is a decision for the owner**, and it is the same decision the
Revision 5 analysis reached: **a declared dependency is the lesser
risk** than an unreviewed implementation of the one component that
carries the security.

---

## 5. The honest summary

| Platform | Minimum | Hardware-backed? | Acceptable as the trust anchor? |
|---|---|---|---|
| Android 13+ | API 33 | Usually (TEE); StrongBox on some | **Yes** |
| Android 9–12 | API 28 | Usually (TEE) | **Yes** |
| Android 6–8 | API 23 | Sometimes | **Only if the tier is verified at enrolment** |
| Android with software-only keystore | any | **No** | **With a disclosed caveat, and a stronger recovery story** |
| iOS 13+ | iOS 13 | **Always** | **Yes** |
| iOS 11–12 | iOS 11 | Always | Yes (passcode fallback) |

**The platform must not silently accept a software-only Android key as
equivalent to a Secure Enclave key.** Either it refuses, or it records
the tier and shows it to the user at enrolment, permanently.

---

## 6. Implementation status

**NOT IMPLEMENTED.** The matrix is a design specification; no platform
code exists.

What **is** implemented and tested is the platform-independent part: the
canonical form, the hash binding, the nine verification checks, the
nonce, the expiry and the revocation check. Those are the same on every
platform, and they are what the phone's key ultimately attests to.

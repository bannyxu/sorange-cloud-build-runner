# SOrange Cloud Build Runner

This public repository contains only the GitHub Actions control plane used to
package SOrange desktop releases. Application source is checked out from
`Burns1028/sorange` at the requested revision, resolved once to an exact
commit SHA, and every platform job builds that same SHA.

No application source or release credentials are stored in this repository.
Credentials are provided through GitHub Actions secrets.


## Windows repair validation

`windows-installer-e2e.yml` builds on a native Windows runner with pnpm 10.27.0.
It checks out the requested private app source and pins the resolved commit for
both Windows 2022 and Windows 2025 installation validation. The selected source
must contain the current runtime builder and private filesystem regression test.

Before packaging, the workflow builds the pinned Windows x64 runtime from that
source, exports its explicit artifact directory, and runs the Windows ACL/root
binding regression. Packaging uses `@sorange/desktop`, verifies package contents,
and keeps publishing disabled. It uploads only temporary Actions artifacts;
there are no website callbacks or public release changes in this validation flow.
Installation validation retains the existing two-or-three-cycle install, upgrade,
startup and uninstall checks. A passing runner does not replace testing the
reported failure on the affected user's Windows machine and existing data.

For the 2.0.40 startup repair, use app source commit
`5e3dcd5dbc4e7182f5995518e10aa434f84709a3`, version `2.0.40`, and two cycles.

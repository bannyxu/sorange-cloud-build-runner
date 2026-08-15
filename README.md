# SOrange Cloud Build Runner

This public repository contains only the GitHub Actions control plane used to
package SOrange desktop releases. Application source is checked out from
`Burns1028/sorange` at the requested revision, resolved once to an exact
commit SHA, and every platform job builds that same SHA.

No application source or release credentials are stored in this repository.
Credentials are provided through GitHub Actions secrets.

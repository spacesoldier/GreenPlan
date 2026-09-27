# Local ODA File Converter runtime

This directory keeps the locally obtained ODA File Converter outside Docker images.

- package: `packages/ODAFileConverter_QT6_lnxX64_8.3dll_27.1.deb`
- package size: `56,204,274` bytes
- SHA-256: `c71363cd54758177af47a365154f180dc50a1e2b52a131994fda541c13a36766`
- extracted runtime: `runtime/usr/bin/ODAFileConverter_27.1.0.0/`
- official source: `https://www.opendesign.com/guestfiles/oda_file_converter`

The package and extracted proprietary binaries are local runtime dependencies. Do not
redistribute them or bake them into a public Docker image without a separate licence
review. The platform bind-mounts the extracted directory read-only.

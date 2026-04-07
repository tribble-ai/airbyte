from setuptools import find_packages, setup

setup(
    name="source_gong_transcripts",
    version="0.1.0",
    description="Gong Transcripts source connector with sentence extraction",
    author="Your Team",
    packages=find_packages(),
    install_requires=[
        "airbyte-cdk>=0.50.0",
    ],
    package_data={
        "": ["*.yaml", "*.yml"],
    },
    python_requires=">=3.9",
)

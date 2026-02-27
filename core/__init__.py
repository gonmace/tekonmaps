# Suprimir RequestsDependencyWarning por incompatibilidad urllib3/charset_normalizer
import warnings
warnings.filterwarnings("ignore", message=".*doesn't match a supported version.*")

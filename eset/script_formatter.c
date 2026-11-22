#include "script_formatter.h"
#include "common.h"

void Script_Formatter_init(Script_Formatter* restrict sf, FILE* outFile)
{
	sf->outFile = outFile;
	sf->indent = 0;
}

void Script_Formatter_print_indent(const Script_Formatter* restrict sf)
{
	for (int i = 0; i < sf->indent; i += 1) {
		fputc('\t', sf->outFile);
	}
}

void Script_Formatter_printf(const Script_Formatter* restrict sf, const char* restrict __format, ...)
{
	Script_Formatter_print_indent(sf);

	va_list ap;
	va_start(ap, __format);

	vfprintf(sf->outFile, __format, ap);

	va_end(ap);
}

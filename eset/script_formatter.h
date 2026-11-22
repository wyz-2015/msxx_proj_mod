#ifndef _SCRIPT_FORMATTER_H
#define _SCRIPT_FORMATTER_H

#include <stdio.h>

typedef struct Script_Formatter {
	FILE* outFile;
	int indent;
} Script_Formatter;

void Script_Formatter_init(Script_Formatter* __restrict sf, FILE* outFile);
void Script_Formatter_printf(const Script_Formatter* __restrict sf, const char* __restrict __format, ...);
#define Script_Formatter_indent_add(sf, n) (sf)->indent += (n)

#endif

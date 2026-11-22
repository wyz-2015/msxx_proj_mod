#include "common.h"
#include "script_formatter.h"

void parser_cond(FILE* restrict esetFile, Script_Formatter* restrict sf)
{
	// TODO
	Script_Formatter_printf(sf, "[...]");
}

void parser_core(FILE* restrict esetFile, Script_Formatter* restrict sf)
{
	uint8_t opCode, size;
	fread(&opCode, sizeof(uint8_t), 1, esetFile);
	fread(&size, sizeof(uint8_t), 1, esetFile);

	switch (opCode) {
	case 0x00: {
		uint16_t gate;
		fread(&gate, sizeof(uint16_t), 1, esetFile);
		Script_Formatter_printf(sf, "gate(0x%x)\n", gate);

		break;
	}
	case 0x01: {
		uint16_t gate, window;
		fread(&gate, sizeof(uint16_t), 1, esetFile);
		fread(&window, sizeof(uint16_t), 1, esetFile);
		Script_Formatter_printf(sf, "gate_lock_window(0x%x, 0x%x)\n", gate, window);

		break;
	}
	case 0x02: {
		uint16_t limit;
		fread(&limit, sizeof(uint16_t), 1, esetFile);
		Script_Formatter_printf(sf, "lock_limit(0x%x)\n", limit);

		break;
	}
	case 0x03: {
		// 未使用，AI推测为自动滚动，待验证 TODO
		Script_Formatter_printf(sf, "auto_scrolling()");

		break;
	}
	case 0x04: {
		// 未使用，AI推测为设活动窗口[window, 最大值]
		uint16_t window;
		fread(&window, sizeof(uint16_t), 1, esetFile);
		Script_Formatter_printf(sf, "window(0x%x)", window);

		break;
	}
	case 0x05: {
		// TODO
		int16_t gotoOffset;
		fread(&gotoOffset, sizeof(int16_t), 1, esetFile);

		Script_Formatter_printf(sf, "if_not([...])\n");
		// Script_Formatter_printf(&sf,"{");
		Script_Formatter_indent_add(sf, 1);
		Script_Formatter_printf(sf, "goto(%d)\n", gotoOffset);
		Script_Formatter_indent_add(sf, -1);

		fseek(esetFile, size - (sizeof(uint8_t) * 2 + sizeof(int16_t)), 1); // 跳过条件解析，暂时

		break;
	}
	case 0x06: {
		uint16_t frames;
		fread(&frames, sizeof(uint16_t), 1, esetFile);

		Script_Formatter_printf(sf, "wait_frames(0x%x)\n", frames);

		break;
	}
	case 0x07: {
		Script_Formatter_printf(sf, "counter_clear()\n");
		break;
	}
	case 0x08: {
		uint8_t group, flags;
		uint16_t x, y;
		uint16_t unitID;

		fread(&group, sizeof(uint8_t), 1, esetFile);
		fread(&flags, sizeof(uint8_t), 1, esetFile);
		fread(&x, sizeof(int16_t), 1, esetFile);
		fread(&y, sizeof(int16_t), 1, esetFile);
		fread(&unitID, sizeof(uint16_t), 1, esetFile);

		uint16_t paramLen = (size - 10) / sizeof(uint16_t);
		uint16_t unitParams[paramLen];
		fread(unitParams, sizeof(uint16_t), paramLen, esetFile);

		Script_Formatter_printf(sf, "spawn(0x%x, 0x%x, 0x%x, 0x%x, Unit_0x%x(", group, flags, x, y, unitID);
		for (uint16_t i = 0; i < paramLen - 1; i += 1) {
			fprintf(sf->outFile, "0x%x, ", unitParams[i]);
		}
		fprintf(sf->outFile, "0x%x))\n", unitParams[paramLen - 1]);

		break;
	}
	case 0x09: {
		uint16_t subLen, group, clearScroll;
		fread(&subLen, sizeof(uint16_t), 1, esetFile);
		fread(&group, sizeof(uint16_t), 1, esetFile);
		fread(&clearScroll, sizeof(uint16_t), 1, esetFile);

		Script_Formatter_printf(sf, "spawn_cond(0x%x, 0x%x, 0x%x, ", subLen, group, clearScroll);

		parser_cond(esetFile, sf);
		fputs(", ", sf->outFile);
		parser_cond(esetFile, sf);
		fputs(")\n", sf->outFile);
		fseek(esetFile, size - (sizeof(uint16_t) * 3 + sizeof(uint8_t) * 2), 1); // 暂时跳过解析

		Script_Formatter_indent_add(sf, 1);
		parser_core(esetFile, sf);
		Script_Formatter_indent_add(sf, -1);

		break;
	}
	case 0x0a: {
		Script_Formatter_printf(sf, "if(");

		parser_cond(esetFile, sf);
		fseek(esetFile, size - (sizeof(uint8_t) * 2), 1); // 暂时跳过解析
		fputs(")\n", sf->outFile);

		Script_Formatter_indent_add(sf, 1);
		parser_core(esetFile, sf);
		Script_Formatter_indent_add(sf, 1);

		break;
	}
	case 0x0b: {
		// TODO
		// break;
	}
	default: {
		error(EINVAL, EINVAL, "暂不支持的opCode：0x%x。当前位置：0x%lx", opCode, ftell(esetFile));
	}
	}
}

void parser_main(FILE* restrict esetFile, FILE* restrict outFile)
{
	Script_Formatter sf;
	Script_Formatter_init(&sf, outFile);

	uint16_t varientOffset;
	fread(&varientOffset, sizeof(uint16_t), 1, esetFile);
	Script_Formatter_printf(&sf, "varientOffset(0x%x)\n", varientOffset);

	while (not feof_(esetFile)) {
		parser_core(esetFile, &sf);
	}
}
